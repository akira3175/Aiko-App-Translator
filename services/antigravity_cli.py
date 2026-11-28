"""Local Antigravity CLI (`agy`) discovery, model listing, and status service."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


_CACHE_TTL = 60.0
_lock = threading.RLock()
_models_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}


def subprocess_window_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def resolve_agy_binary(custom_path: str = "") -> str | None:
    configured = str(custom_path or "").strip()
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        direct = Path(expanded)
        if direct.is_file():
            return str(direct.resolve())
        found = shutil.which(expanded)
        if found:
            return str(Path(found).resolve())
        raise RuntimeError(f"Không tìm thấy lệnh Antigravity CLI tại đường dẫn: {configured}")

    which_path = shutil.which("agy")
    if which_path:
        return str(Path(which_path).resolve())

    exe_name = "agy.exe" if os.name == "nt" else "agy"
    candidates = [
        Path.home() / ".gemini" / "bin" / exe_name,
        Path.home() / ".local" / "bin" / exe_name,
    ]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            base = Path(local_app_data)
            candidates.extend([
                base / "Programs" / "Antigravity" / exe_name,
                base / "Antigravity" / exe_name,
            ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def _parse_models_output(stdout: str) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_line in str(stdout or "").splitlines():
        line = raw_line.strip()
        if "\t" not in line:
            continue
        slug, display_name = line.split("\t", 1)
        slug = slug.strip()
        display_name = display_name.strip() or slug
        if slug and slug not in seen:
            seen.add(slug)
            models.append({"slug": slug, "display_name": display_name})
    return models


def _format_cli_error(detail: str) -> str:
    lowered = detail.lower()
    if any(token in lowered for token in ("authentication required", "unauthenticated", "not logged in", "sign in", "login")):
        return (
            "Chưa đăng nhập Antigravity CLI. Hãy bấm “Mở Terminal agy” trong "
            "Cài đặt → Antigravity CLI (hoặc mở terminal chạy lệnh agy) để đăng nhập một lần."
        )
    return f"Không lấy được danh sách model từ Antigravity CLI: {detail or 'phản hồi trống'}"


def cli_version(custom_path: str = "") -> str:
    binary = resolve_agy_binary(custom_path)
    if not binary:
        return ""
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            **subprocess_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    return lines[0] if lines else ""


def list_models(custom_path: str = "", *, refresh: bool = False) -> list[dict[str, str]]:
    binary = resolve_agy_binary(custom_path)
    if not binary:
        raise RuntimeError(
            "Không tìm thấy Antigravity CLI (agy). Hãy cài đặt Antigravity CLI "
            "hoặc nhập đường dẫn agy.exe trong Cài đặt → Antigravity CLI."
        )
    now = time.monotonic()
    with _lock:
        cached = _models_cache.get(binary)
        if not refresh and cached and (now - cached[0]) < _CACHE_TTL and cached[1]:
            return [dict(item) for item in cached[1]]

    try:
        completed = subprocess.run(
            [binary, "models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            **subprocess_window_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Antigravity CLI phản hồi quá thời gian khi tải danh sách model.") from exc
    except OSError as exc:
        raise RuntimeError(f"Không thể khởi chạy Antigravity CLI: {exc}") from exc

    models = _parse_models_output(completed.stdout)
    if completed.returncode != 0 or not models:
        detail = ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()
        detail_lines = [
            line.strip()
            for line in detail.splitlines()
            if line.strip() and "fetching available models" not in line.lower()
        ]
        raise RuntimeError(_format_cli_error(" ".join(detail_lines)[:400]))

    with _lock:
        _models_cache[binary] = (time.monotonic(), models)
    return [dict(item) for item in models]


def default_model(custom_path: str = "") -> str:
    models = list_models(custom_path)
    if not models:
        raise RuntimeError(
            "Tài khoản Antigravity CLI chưa có model khả dụng. Hãy kiểm tra trong Cài đặt → Antigravity CLI."
        )
    return models[0]["slug"]


class AntigravityCliService:
    def __init__(self, configuration=None):
        self._configuration = configuration

    def _custom_path(self) -> str:
        if self._configuration is None:
            return ""
        try:
            saved = self._configuration.saved_settings()
        except Exception:
            return ""
        return str(saved.get("antigravity_cli_path", "")).strip()

    def status(self, *, refresh: bool = False) -> dict:
        custom_path = self._custom_path()
        try:
            binary = resolve_agy_binary(custom_path)
        except RuntimeError as exc:
            return {
                "installed": False,
                "connected": False,
                "version": "",
                "binary": custom_path,
                "models": [],
                "error": str(exc),
            }

        if not binary:
            return {
                "installed": False,
                "connected": False,
                "version": "",
                "binary": "",
                "models": [],
                "error": "Chưa tìm thấy lệnh agy trên máy. Hãy cài đặt Antigravity CLI hoặc điền đường dẫn agy.exe bên dưới.",
            }

        version = cli_version(custom_path)
        try:
            models = list_models(custom_path, refresh=refresh)
            return {
                "installed": True,
                "connected": bool(models),
                "version": version,
                "binary": binary,
                "models": models,
                "error": "",
            }
        except (RuntimeError, OSError) as exc:
            return {
                "installed": True,
                "connected": False,
                "version": version,
                "binary": binary,
                "models": [],
                "error": str(exc),
            }

    def open_terminal(self) -> dict:
        custom_path = self._custom_path()
        binary = resolve_agy_binary(custom_path)
        if not binary:
            raise RuntimeError(
                "Không tìm thấy lệnh agy để mở. Hãy cài đặt Antigravity CLI hoặc lưu đường dẫn agy.exe trước."
            )
        if os.name == "nt":
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "Antigravity CLI", binary],
                **subprocess_window_kwargs(),
            )
        else:
            raise RuntimeError("Mở cửa sổ Terminal tự động hiện chỉ hỗ trợ Windows. Hãy chạy lệnh agy trong terminal.")
        return {
            "ok": True,
            "binary": binary,
            "message": "Đã mở cửa sổ Antigravity CLI. Bạn có thể đăng nhập hoặc gõ /usage để xem hạn mức.",
        }
