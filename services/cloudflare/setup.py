"""Provision Cloudflare Workers and R2 buckets without application-state access."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def cloudflare_api(
    account_id: str,
    api_token: str,
    method: str,
    path: str,
    body=None,
    headers=None,
):
    url = (
        f"https://api.cloudflare.com/client/v4{path}"
        if path.startswith("/user/")
        else f"https://api.cloudflare.com/client/v4/accounts/{account_id}{path}"
    )
    request_headers = {"Authorization": f"Bearer {api_token}", **(headers or {})}
    data = body
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    try:
        request = Request(url, data=data, headers=request_headers, method=method)
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            error_payload = json.loads(error.read().decode("utf-8"))
            message = "; ".join(
                str(item.get("message", ""))
                for item in error_payload.get("errors", [])
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(error.reason)
        raise ValueError(
            f"Cloudflare trả lỗi {error.code}: {message or error.reason}"
        ) from None
    except URLError as error:
        raise ValueError(f"Không kết nối được Cloudflare: {error.reason}") from None
    if not payload.get("success", False):
        message = "; ".join(
            str(item.get("message", "")) for item in payload.get("errors", [])
        )
        raise ValueError(message or "Cloudflare từ chối yêu cầu")
    return payload.get("result")


def _validate_credentials(payload: dict, default_bucket: str):
    account_id = str(payload.get("account_id", "")).strip()
    api_token = str(payload.get("api_token", "")).strip()
    bucket = str(payload.get("bucket", "")).strip() or default_bucket
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
        raise ValueError("Cloudflare Account ID phải gồm 32 ký tự hex")
    if not api_token or len(api_token) > 500:
        raise ValueError("API Token không hợp lệ")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", bucket):
        raise ValueError("Tên bucket phải gồm 3–64 ký tự thường, số hoặc dấu gạch ngang")
    return account_id, api_token, bucket


def _r2_credentials(account_id, api_token, bucket, api_call):
    identity = api_call(account_id, api_token, "GET", "/user/tokens/verify") or {}
    access_key_id = str(identity.get("id", "")).strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", access_key_id):
        raise ValueError("Cloudflare không trả về ID hợp lệ cho API Token")
    secret_access_key = hashlib.sha256(api_token.encode("utf-8")).hexdigest()
    result = api_call(account_id, api_token, "GET", "/r2/buckets") or {}
    bucket_names = {item.get("name") for item in result.get("buckets", [])}
    bucket_created = bucket not in bucket_names
    if bucket_created:
        api_call(account_id, api_token, "POST", "/r2/buckets", {"name": bucket})
    return access_key_id, secret_access_key, bucket_created


def _multipart_worker(source: bytes, bucket: str):
    boundary = f"----Aiko{secrets.token_hex(16)}"
    metadata = json.dumps(
        {
            "main_module": "index.js",
            "compatibility_date": datetime.now(timezone.utc).date().isoformat(),
            "bindings": [
                {"type": "r2_bucket", "name": "SHARE_BUCKET", "bucket_name": bucket}
            ],
        }
    ).encode("utf-8")
    chunks = []
    for name, filename, content_type, value in (
        ("metadata", None, "application/json", metadata),
        ("index.js", "index.js", "application/javascript+module", source),
    ):
        disposition = f'form-data; name="{name}"' + (
            f'; filename="{filename}"' if filename else ""
        )
        chunks.append(
            (
                f"--{boundary}\r\nContent-Disposition: {disposition}\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + value
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def deploy_share_worker(payload: dict, project_root: Path, api_call=cloudflare_api):
    account_id, api_token, bucket = _validate_credentials(payload, "private-shares")
    worker_name = str(payload.get("worker_name", "aiko-share-reader")).strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", worker_name):
        raise ValueError("Tên Worker phải gồm 1–63 ký tự thường, số hoặc dấu gạch ngang")
    access_key_id, secret_access_key, bucket_created = _r2_credentials(
        account_id, api_token, bucket, api_call
    )
    source = (project_root / "cloudflare" / "share-worker" / "src" / "index.js").read_bytes()
    worker_body, content_type = _multipart_worker(source, bucket)
    script_path = f"/workers/scripts/{quote(worker_name, safe='')}"
    api_call(
        account_id,
        api_token,
        "PUT",
        script_path,
        worker_body,
        {"Content-Type": content_type},
    )
    try:
        subdomain_result = api_call(
            account_id, api_token, "GET", "/workers/subdomain"
        ) or {}
    except ValueError:
        subdomain_result = {}
    account_subdomain = str(subdomain_result.get("subdomain", "")).strip()
    if not account_subdomain:
        generated = "aiko-" + hashlib.sha256(account_id.encode("ascii")).hexdigest()[:10]
        result = api_call(
            account_id,
            api_token,
            "PUT",
            "/workers/subdomain",
            {"subdomain": generated},
        ) or {}
        account_subdomain = str(result.get("subdomain", generated)).strip()
    api_call(
        account_id,
        api_token,
        "POST",
        f"{script_path}/subdomain",
        {"enabled": True, "previews_enabled": False},
    )
    worker_url = f"https://{worker_name}.{account_subdomain}.workers.dev"
    return {
        "bucket_created": bucket_created,
        "worker_url": worker_url,
        "settings": {
            "share_r2_account_id": account_id,
            "share_r2_access_key_id": access_key_id,
            "share_r2_secret_access_key": secret_access_key,
            "share_r2_bucket": bucket,
            "share_worker_url": worker_url,
        },
    }


def setup_publishing_r2(payload: dict, api_call=cloudflare_api):
    account_id, api_token, bucket = _validate_credentials(payload, "aiko-images")
    access_key_id, secret_access_key, bucket_created = _r2_credentials(
        account_id, api_token, bucket, api_call
    )
    managed = api_call(
        account_id,
        api_token,
        "PUT",
        f"/r2/buckets/{quote(bucket, safe='')}/domains/managed",
        {"enabled": True},
    ) or {}
    public_domain = str(managed.get("domain", "")).strip()
    if not public_domain:
        raise ValueError("Cloudflare chưa trả về đường dẫn public của bucket")
    public_url = f"https://{public_domain}"
    return {
        "bucket_created": bucket_created,
        "public_url": public_url,
        "settings": {
            "r2_account_id": account_id,
            "r2_access_key_id": access_key_id,
            "r2_secret_access_key": secret_access_key,
            "r2_bucket": bucket,
            "r2_public_url": public_url,
        },
    }
