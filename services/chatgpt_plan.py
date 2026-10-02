"""Local Sign in with ChatGPT session for the experimental plan provider."""

import base64
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import uuid

from cores.config.project_paths import USER_DATA_ROOT


AUTH = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
STORE = USER_DATA_ROOT / "chatgpt-plan.dpapi"
_lock = threading.RLock()


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(data, *, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Đăng nhập ChatGPT hiện chỉ hỗ trợ Windows.")
    source, buffer = _blob(data)
    result = _Blob()
    method = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if decrypt:
        ok = method(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result))
    else:
        ok = method(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result))
    if not ok:
        raise OSError(ctypes.get_last_error(), "Không thể đọc hoặc lưu phiên ChatGPT")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(result.pbData)


@contextmanager
def _process_lock():
    import msvcrt
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE.with_suffix(".lock"), "a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        for _ in range(100):
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Không thể khóa phiên ChatGPT để làm mới token.")
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _read():
    if not STORE.exists():
        return {}
    return json.loads(_protect(STORE.read_bytes(), decrypt=True).decode("utf-8"))


def _write(value):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STORE.with_name(STORE.name + ".tmp")
    temporary.write_bytes(_protect(json.dumps(value).encode("utf-8")))
    os.replace(temporary, STORE)


def _request_json(url, *, data=None, headers=None):
    body = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, body, headers=headers or {}, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except HTTPError as exc:
        raise RuntimeError(f"OpenAI trả về HTTP {exc.code}.") from exc


def _b64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _validated_identity(token, client_id, nonce):
    """Verify the OIDC signature and claims before accepting any credential."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError("ID token không hợp lệ.")
    header = json.loads(_b64(parts[0]))
    claims = json.loads(_b64(parts[1]))
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise RuntimeError("Thuật toán ID token không được hỗ trợ.")
    discovery = _request_json(AUTH + "/.well-known/openid-configuration")
    jwks_uri = str(discovery.get("jwks_uri", ""))
    if not jwks_uri.startswith(AUTH + "/"):
        raise RuntimeError("Địa chỉ JWKS không hợp lệ.")
    keys = _request_json(jwks_uri).get("keys", [])
    key = next((item for item in keys if item.get("kid") == header["kid"] and item.get("kty") == "RSA"), None)
    if not key:
        raise RuntimeError("Không tìm thấy khóa xác minh ID token.")
    public = rsa.RSAPublicNumbers(int.from_bytes(_b64(key["e"]), "big"), int.from_bytes(_b64(key["n"]), "big")).public_key()
    public.verify(_b64(parts[2]), (parts[0] + "." + parts[1]).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    audience = claims.get("aud")
    if (claims.get("iss") != AUTH or client_id not in (audience if isinstance(audience, list) else [audience])
            or claims.get("nonce") != nonce or float(claims.get("exp", 0)) <= time.time()
            or not claims.get("sub")):
        raise RuntimeError("Thông tin xác thực ID token không khớp.")
    return claims


def _refresh(record):
    response = _request_json(AUTH + "/api/accounts/oauth/token", data={
        "grant_type": "refresh_token", "client_id": record["client_id"],
        "refresh_token": record["refresh_token"], "resource": RESOURCE,
    })
    if not response.get("access_token") or not response.get("refresh_token"):
        raise RuntimeError("Không thể làm mới phiên ChatGPT; hãy đăng nhập lại.")
    record.update({
        "access_token": response["access_token"], "refresh_token": response["refresh_token"],
        "expires_at": time.time() + int(response.get("expires_in", 3600)),
        "scopes": response.get("scope", "").split() or record.get("scopes", []),
    })
    _write(record)
    return record


def access_token():
    with _lock:
        with _process_lock():
            record = _read()
            if not record.get("access_token") or "chatgpt.tokens.use.direct" not in record.get("scopes", []):
                raise RuntimeError("Chưa đăng nhập ChatGPT hoặc tài khoản chưa cấp quyền dùng gói ChatGPT.")
            if record.get("expires_at", 0) <= time.time() + 90:
                record = _refresh(record)
            return record["access_token"]


def list_models():
    data = _request_json(RESOURCE + "/models", headers={"Authorization": "Bearer " + access_token()})
    return [{"slug": item["slug"], "display_name": item.get("display_name", item["slug"])}
            for item in data.get("models", []) if item.get("visibility") == "list" and item.get("slug")]


def default_model():
    models = list_models()
    if not models:
        raise RuntimeError("Tài khoản ChatGPT chưa có model khả dụng. Hãy kiểm tra quyền truy cập trong Cài đặt.")
    return models[0]["slug"]


class ChatGptPlanService:
    def __init__(self):
        self.pending = None
        self.error = ""

    def status(self):
        with _lock:
            record = _read()
        connected = bool(record.get("access_token") and "chatgpt.tokens.use.direct" in record.get("scopes", []))
        result = {"connected": connected, "email": record.get("email", ""), "error": self.error}
        if connected:
            try:
                result["models"] = list_models()
            except (RuntimeError, OSError) as exc:
                result["models"] = []
                result["error"] = str(exc)
        return result

    def connect(self):
        with _lock:
            with _process_lock():
                record = _read()
                if not record.get("host_id"):
                    record["host_id"] = "urn:uuid:" + str(uuid.uuid4())
                    _write(record)
            if self.pending:
                self.pending["server"].server_close()
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            service = self

            class Callback(BaseHTTPRequestHandler):
                def do_GET(self):
                    if urlparse(self.path).path != "/auth/callback":
                        self.send_error(404)
                        return
                    query = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
                    if query.get("state") != state:
                        self.send_error(400, "OAuth state mismatch")
                        return
                    try:
                        service._complete(query)
                        message = "Đã kết nối ChatGPT. Bạn có thể quay lại ứng dụng."
                    except Exception as exc:
                        service.error = str(exc) if isinstance(exc, (RuntimeError, OSError, ValueError, KeyError)) else "Không xác minh được phiên đăng nhập ChatGPT."
                        message = "Không thể kết nối ChatGPT. Hãy quay lại ứng dụng để xem lỗi."
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(message.encode("utf-8"))
                    service.pending = None

                def log_message(self, *args):
                    pass

            server = HTTPServer(("127.0.0.1", 0), Callback)
            server.timeout = 300
            redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
            client_id = record.get("client_id") or "dynamic_agent_client"
            self.pending = {"server": server, "state": state, "nonce": nonce,
                            "verifier": verifier, "redirect": redirect, "client_id": client_id,
                            "subject": record.get("subject", "")}
            self.error = ""
            params = {
                "client_id": client_id, "ext_agent_host_id": record["host_id"],
                "response_type": "code", "redirect_uri": redirect, "scope": SCOPES,
                "resource": RESOURCE, "state": state, "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("="),
            }
            if client_id == "dynamic_agent_client":
                params["agent_name_hint"] = "Aiko Translator"
            elif record.get("email"):
                params["login_hint"] = record["email"]
            threading.Thread(target=self._serve, args=(server,), daemon=True).start()
            return {"url": AUTH + "/api/accounts/authorize?" + urlencode(params)}

    def _serve(self, server):
        try:
            deadline = time.monotonic() + 300
            while self.pending and self.pending.get("server") is server and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()
            if self.pending and self.pending.get("server") is server:
                self.pending = None

    def _complete(self, query):
        pending = self.pending
        if not pending or query.get("state") != pending["state"]:
            raise RuntimeError("Phiên đăng nhập đã hết hạn.")
        if query.get("error"):
            raise RuntimeError("ChatGPT từ chối quyền đăng nhập.")
        issued = query.get("client_id", "")
        if pending["client_id"] == "dynamic_agent_client":
            if not issued:
                raise RuntimeError("OpenAI không trả về client ID.")
            client_id = issued
        else:
            client_id = pending["client_id"]
            if issued and issued != client_id:
                raise RuntimeError("Client ID không khớp.")
        response = _request_json(AUTH + "/api/accounts/oauth/token", data={
            "grant_type": "authorization_code", "client_id": client_id,
            "code": query["code"], "code_verifier": pending["verifier"],
            "redirect_uri": pending["redirect"], "resource": RESOURCE,
        })
        identity = _validated_identity(response["id_token"], client_id, pending["nonce"])
        if pending["subject"] and identity["sub"] != pending["subject"]:
            raise RuntimeError("Tài khoản ChatGPT không khớp tài khoản đã kết nối.")
        scopes = response.get("scope", "").split()
        if "chatgpt.tokens.use.direct" not in scopes:
            raise RuntimeError("Tài khoản chưa cấp quyền dùng gói ChatGPT.")
        with _lock:
            with _process_lock():
                old = _read()
                _write({"host_id": old["host_id"], "client_id": client_id,
                        "subject": identity["sub"], "email": identity.get("email", ""),
                        "id_token": response["id_token"], "access_token": response["access_token"],
                        "refresh_token": response["refresh_token"], "scopes": scopes,
                        "expires_at": time.time() + int(response.get("expires_in", 3600))})
        self.error = ""

    def disconnect(self):
        with _lock:
            if self.pending:
                self.pending["server"].server_close()
                self.pending = None
            with _process_lock():
                record = _read()
                warning = ""
                if record.get("refresh_token"):
                    try:
                        discovery = _request_json(AUTH + "/.well-known/openid-configuration")
                        endpoint = discovery.get("revocation_endpoint", "")
                        if not endpoint.startswith(AUTH + "/"):
                            raise RuntimeError("Địa chỉ thu hồi phiên không hợp lệ.")
                        _request_json(endpoint, data={"token": record["refresh_token"],
                                                      "token_type_hint": "refresh_token", "client_id": record["client_id"]})
                    except (RuntimeError, OSError, ValueError):
                        warning = "Đã xóa phiên trên máy; chưa xác nhận thu hồi trên OpenAI."
                _write({"host_id": record.get("host_id", "urn:uuid:" + str(uuid.uuid4())),
                        "client_id": record.get("client_id", ""), "subject": record.get("subject", ""),
                        "email": record.get("email", "")})
            return {"ok": True, "warning": warning}
