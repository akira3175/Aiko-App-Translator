"""Check GitHub release metadata for application updates."""

import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def version_parts(value):
    match = re.fullmatch(
        r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value).strip()
    )
    if not match:
        raise ValueError(f"Phiên bản không hợp lệ: {value}")
    return tuple(int(part) for part in match.groups())


def payload(
    check_remote,
    current_version,
    repository,
    release_api,
    asset_name,
    opener=urlopen,
):
    result = {
        "current_version": current_version,
        "repository": repository,
        "configured": True,
        "status": "ready",
        "update_available": False,
    }
    if not check_remote:
        return result
    request = Request(
        release_api,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"NovelTranslatorStudio/{current_version}",
        },
    )
    try:
        with opener(request, timeout=15) as response:
            if int(response.headers.get("Content-Length", "0") or 0) > 1_000_000:
                raise ValueError("Dữ liệu release từ GitHub quá lớn")
            raw = response.read(1_000_001)
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            result["status"] = "no_release"
            return result
        raise
    if len(raw) > 1_000_000:
        raise ValueError("Dữ liệu release từ GitHub quá lớn")
    try:
        release = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("GitHub trả về dữ liệu release không hợp lệ") from None
    if not isinstance(release, dict):
        raise ValueError("Dữ liệu release GitHub không hợp lệ")

    latest = str(release.get("tag_name", "")).strip().removeprefix("v")
    asset = next(
        (
            item
            for item in release.get("assets", [])
            if isinstance(item, dict) and item.get("name") == asset_name
        ),
        None,
    )
    download_url = str((asset or {}).get("browser_download_url", "")).strip()
    digest = str((asset or {}).get("digest", "")).strip().lower()
    checksum = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
    latest_parts = version_parts(latest)
    current_parts = version_parts(current_version)
    if download_url:
        download = urlparse(download_url)
        if download.scheme not in {"https", "http"} or not download.netloc:
            raise ValueError("Đường dẫn tải bản cập nhật không hợp lệ")
    if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("SHA-256 trong manifest không hợp lệ")
    available = latest_parts > current_parts
    result.update(
        {
            "status": "update_available" if available else "up_to_date",
            "latest_version": latest,
            "update_available": available,
            "notes": str(release.get("body", "")).strip()[:2000],
            "release_url": str(release.get("html_url", "")).strip(),
            "asset_found": bool(asset),
            "download_ready": bool(download_url and checksum),
            "download_url": download_url,
            "sha256": checksum,
        }
    )
    return result
