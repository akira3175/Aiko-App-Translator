from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import ipaddress
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
LIBRARY = ROOT / "truyen"
HOST, PORT = "127.0.0.1", 8765
MAX_PROJECT_NAME_LENGTH = 60
VERSION_FILE = ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0.0-dev"
GITHUB_REPOSITORY = "akira3175/Aiko-App-Translator"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
UPDATE_ASSET_NAME = "NovelTranslatorStudio-Windows-x64.zip"
UPDATE_DIR = ROOT / ".runtime" / "updates"
UPDATER_SOURCE = ROOT / "apply_update.ps1"

PIPELINES = {
    "v1": ROOT / "cores" / "dich_v1.py",
    "v1-interactions": ROOT / "cores" / "dich_interactions.py",
    "v2": ROOT / "cores" / "dich_v2.py",
    "v3": ROOT / "cores" / "dich_v3.py",
    "gpt": ROOT / "cores" / "dich_gpt.py",
    "gpt-api": ROOT / "cores" / "dich_gpt_api.py",
    "manual": ROOT / "cores" / "dich_v2_manual.py",
    "review": ROOT / "cores" / "review_all.py",
    "characters": ROOT / "cores" / "gen_characters.py",
    "context-api": ROOT / "cores" / "gen_context_api.py",
    "context-v1": ROOT / "cores" / "gen_context_v1.py",
    "context-gpt": ROOT / "cores" / "gen_context_gpt.py",
    "glossary": ROOT / "cores" / "insert_glossary.py",
    "split-review": ROOT / "cores" / "split_review.py",
    "hako": ROOT / "up" / "up_md.py",
}
jobs: dict[str, dict] = {}
job_processes: dict[str, subprocess.Popen] = {}
job_stream_events: dict[str, list[dict]] = {}
TRANSLATION_KINDS = {"v1", "v1-interactions", "v2", "v3", "gpt", "gpt-api", "manual"}
TRANSLATION_LOCK = ROOT / ".runtime" / "translation.lock"
translation_guard = threading.RLock()
lan_sessions: set[str] = set()
lan_login_attempts: dict[str, list[float]] = {}

SETTINGS_FILE = ROOT / ".runtime" / "settings.json"
GEMINI_API_KEYS_FILE = ROOT / "apikeys.txt"
SETTING_DEFAULTS = {
    "link_gemini": "https://gemini.google.com/gem/fdec65ac9c69",
    "translate_model": "gemini-3.5-flash",
    "polish_model": "gemini-3-flash-preview",
    "review_bg_model": "gemini-3.1-flash-lite-preview",
    "review_model": "gemini-3.1-flash-lite-preview",
    "context_model": "gemini-3.5-flash",
    "gemini_api_thinking": "high",
    "gemini_api_temperature": "",
    "gemini_api_top_p": "",
    "gemini_api_top_k": "",
    "gemini_api_max_output_tokens": "",
    "gemini_web_model": "pro",
    "gemini_thinking": "extended",
    "chatgpt_model": "gpt-5.6 sol",
    "chatgpt_thinking": "cao",
    "fix_max_retry": 3,
    "previous_context_chapters": 3,
    "hako_username": "",
    "hako_password": "",
    "hako_management_url": "",
    "r2_account_id": "",
    "r2_access_key_id": "",
    "r2_secret_access_key": "",
    "r2_bucket": "",
    "r2_public_url": "",
    "gpt_api_key": "",
    "gpt_api_endpoint": "https://api.openai.com/v1/responses",
    "gpt_api_translate_model": "gpt-5.6-luna",
    "gpt_api_polish_model": "gpt-5.6-terra",
    "gpt_api_translate_effort": "medium",
    "gpt_api_polish_effort": "high",
    "gpt_api_max_output_tokens": 30000,
    "gpt_api_timeout": 300,
    "gpt_api_retries": 3,
    "gpt_api_temperature": "",
    "lan_enabled": "off",
    "lan_pin": "",
}
SETTING_LABELS = {
    "link_gemini": "Đường dẫn Gemini Gem",
    "translate_model": "Model dịch Gemini API",
    "polish_model": "Model hậu dịch",
    "review_bg_model": "Model review chạy nền",
    "review_model": "Model review toàn bộ",
    "context_model": "Model tạo context",
    "gemini_api_thinking": "Cấp độ suy nghĩ",
    "gemini_api_temperature": "Temperature",
    "gemini_api_top_p": "Top P",
    "gemini_api_top_k": "Top K",
    "gemini_api_max_output_tokens": "Token đầu ra tối đa",
    "gemini_web_model": "Model Gemini Web (free/pro/thinking)",
    "gemini_thinking": "Mức thinking Gemini Web",
    "chatgpt_model": "Model ChatGPT Web",
    "chatgpt_thinking": "Mức thinking ChatGPT Web",
    "fix_max_retry": "Số lần sửa ký tự ngoại ngữ",
    "previous_context_chapters": "Số chương trước làm ngữ cảnh dịch",
    "hako_username": "Tên đăng nhập Hako",
    "hako_password": "Mật khẩu Hako",
    "hako_management_url": "Đường dẫn tạo chương Hako",
    "r2_account_id": "R2 Account ID",
    "r2_access_key_id": "R2 Access Key ID",
    "r2_secret_access_key": "R2 Secret Access Key",
    "r2_bucket": "Tên bucket R2",
    "r2_public_url": "Đường dẫn public R2",
    "gpt_api_key": "GPT API key",
    "gpt_api_endpoint": "Endpoint GPT Responses API",
    "gpt_api_translate_model": "Model GPT API dùng để dịch",
    "gpt_api_polish_model": "Model GPT API dùng để hiệu đính",
    "gpt_api_translate_effort": "Reasoning effort khi dịch",
    "gpt_api_polish_effort": "Reasoning effort khi hiệu đính",
    "gpt_api_max_output_tokens": "Số token đầu ra tối đa GPT API",
    "gpt_api_timeout": "Thời gian chờ GPT API (giây)",
    "gpt_api_retries": "Số lần thử lại GPT API",
    "gpt_api_temperature": "Temperature GPT API (để trống = mặc định)",
    "lan_enabled": "Truy cập từ điện thoại cùng Wi-Fi",
    "lan_pin": "Mã PIN truy cập LAN",
}
SECRET_SETTINGS = {"hako_password", "r2_access_key_id", "r2_secret_access_key", "gpt_api_key", "lan_pin"}
SETTING_RANGES = {
    "fix_max_retry": (1, 20),
    "previous_context_chapters": (0, 20),
    "gpt_api_max_output_tokens": (1000, 128000),
    "gpt_api_timeout": (30, 3600),
    "gpt_api_retries": (1, 10),
}
SETTING_META = {
    "link_gemini": {"group": "gemini-web"},
    "translate_model": {"group": "gemini-api", "description": "Model dùng cho bản dịch chính."},
    "polish_model": {"group": "gemini-api", "description": "Model biên tập sau khi dịch."},
    "review_bg_model": {"group": "gemini-api", "description": "Model review nhanh chạy nền."},
    "review_model": {"group": "gemini-api", "description": "Model dùng khi review toàn bộ truyện."},
    "context_model": {"group": "gemini-api", "description": "Model Gemini API dùng để tạo glossary trong context.yaml."},
    "gemini_api_thinking": {"group": "gemini-api", "type": "select", "options": [
        ["auto", "Tự động theo model"], ["off", "Tắt"], ["minimal", "Minimal"],
        ["low", "Low"], ["medium", "Medium"], ["high", "High"],
    ], "description": "Model không hỗ trợ một mức cụ thể có thể trả lỗi; khi đó chọn Tự động."},
    "gemini_api_temperature": {"group": "gemini-api", "inputmode": "decimal", "description": "Để trống để mỗi công đoạn dùng giá trị riêng. Khoảng 0–2."},
    "gemini_api_top_p": {"group": "gemini-api", "inputmode": "decimal", "description": "Để trống để Gemini tự chọn. Khoảng 0–1."},
    "gemini_api_top_k": {"group": "gemini-api", "inputmode": "numeric", "description": "Để trống để Gemini tự chọn. Số nguyên từ 1."},
    "gemini_api_max_output_tokens": {"group": "gemini-api", "inputmode": "numeric", "description": "Để trống để dùng giới hạn của model."},
    "gemini_web_model": {"group": "gemini-web"},
    "gemini_thinking": {"group": "gemini-web"},
    "chatgpt_model": {"group": "chatgpt-web"},
    "chatgpt_thinking": {"group": "chatgpt-web"},
    "fix_max_retry": {"group": "general"},
    "previous_context_chapters": {"group": "general", "description": "Số bản dịch liền trước được đưa vào prompt. Mặc định: 3."},
    "hako_username": {"group": "publishing"}, "hako_password": {"group": "publishing"},
    "hako_management_url": {"group": "publishing"}, "r2_account_id": {"group": "publishing"},
    "r2_access_key_id": {"group": "publishing"}, "r2_secret_access_key": {"group": "publishing"},
    "r2_bucket": {"group": "publishing"}, "r2_public_url": {"group": "publishing"},
    "gpt_api_key": {"group": "gpt-api"}, "gpt_api_endpoint": {"group": "gpt-api"},
    "gpt_api_translate_model": {"group": "gpt-api"}, "gpt_api_polish_model": {"group": "gpt-api"},
    "gpt_api_translate_effort": {"group": "gpt-api"}, "gpt_api_polish_effort": {"group": "gpt-api"},
    "gpt_api_max_output_tokens": {"group": "gpt-api"}, "gpt_api_timeout": {"group": "gpt-api"},
    "gpt_api_retries": {"group": "gpt-api"}, "gpt_api_temperature": {"group": "gpt-api"},
    "lan_enabled": {
        "group": "general",
        "type": "select",
        "options": [["off", "Tắt (chỉ máy tính này)"], ["on", "Bật trong mạng LAN"]],
        "description": "Cần khởi động lại app sau khi thay đổi.",
    },
    "lan_pin": {
        "group": "general",
        "inputmode": "numeric",
        "description": "6–12 chữ số. Để trống khi bật để app tự sinh mã 6 số.",
    },
}
OPTIONAL_SETTINGS = set(SETTING_DEFAULTS) - {
    "link_gemini", "translate_model", "polish_model", "review_bg_model",
    "review_model", "context_model", "gemini_web_model", "gemini_thinking",
    "chatgpt_model", "chatgpt_thinking", "fix_max_retry",
    "gpt_api_endpoint", "gpt_api_translate_model", "gpt_api_polish_model",
    "gpt_api_translate_effort", "gpt_api_polish_effort",
}


def saved_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key: data[key] for key in SETTING_DEFAULTS if key in data}


def settings_payload():
    saved = saved_settings()
    return {
        "items": [
            {
                "key": key,
                "label": SETTING_LABELS[key],
                "value": saved.get(key, default),
                "default": default,
                "type": "number" if isinstance(default, int) else ("password" if key in SECRET_SETTINGS else "text"),
                "min": SETTING_RANGES.get(key, (None, None))[0],
                "max": SETTING_RANGES.get(key, (None, None))[1],
                "overridden": key in saved,
                **SETTING_META.get(key, {"group": "general"}),
            }
            for key, default in SETTING_DEFAULTS.items()
        ]
    }


def write_settings(payload: dict):
    if payload.get("reset"):
        SETTINGS_FILE.unlink(missing_ok=True)
        return settings_payload()
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError("Dữ liệu cài đặt không hợp lệ")
    cleaned = {}
    for key, default in SETTING_DEFAULTS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{SETTING_LABELS[key]} phải là số nguyên") from None
            minimum, maximum = SETTING_RANGES.get(key, (1, 20))
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"{SETTING_LABELS[key]} phải từ {minimum} đến {maximum}"
                )
        else:
            value = str(value).strip()
            if (not value and key not in OPTIONAL_SETTINGS) or len(value) > 500:
                raise ValueError(f"{SETTING_LABELS[key]} không hợp lệ")
            if value and key == "gemini_api_thinking" and value not in {"auto", "off", "minimal", "low", "medium", "high"}:
                raise ValueError("Cấp độ suy nghĩ Gemini API không hợp lệ")
            if key == "lan_enabled" and value not in {"off", "on"}:
                raise ValueError("Chế độ truy cập LAN không hợp lệ")
            if key == "lan_pin" and value and not re.fullmatch(r"\d{6,12}", value):
                raise ValueError("Mã PIN LAN phải gồm 6–12 chữ số")
            if value and key in {"gemini_api_temperature", "gemini_api_top_p", "gemini_api_top_k", "gemini_api_max_output_tokens"}:
                try:
                    number = float(value)
                except ValueError:
                    raise ValueError(f"{SETTING_LABELS[key]} phải là một số") from None
                limits = {
                    "gemini_api_temperature": (0, 2), "gemini_api_top_p": (0, 1),
                    "gemini_api_top_k": (1, None), "gemini_api_max_output_tokens": (1, None),
                }
                minimum, maximum = limits[key]
                if number < minimum or (maximum is not None and number > maximum):
                    raise ValueError(f"{SETTING_LABELS[key]} nằm ngoài phạm vi cho phép")
                if key in {"gemini_api_top_k", "gemini_api_max_output_tokens"} and not number.is_integer():
                    raise ValueError(f"{SETTING_LABELS[key]} phải là số nguyên")
        if value != default:
            cleaned[key] = value
    if cleaned.get("lan_enabled") == "on" and not cleaned.get("lan_pin"):
        cleaned["lan_pin"] = f"{secrets.randbelow(1_000_000):06d}"
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    if cleaned:
        temporary = SETTINGS_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, SETTINGS_FILE)
    else:
        SETTINGS_FILE.unlink(missing_ok=True)
    return settings_payload()


def version_parts(value: str):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        raise ValueError(f"Phiên bản không hợp lệ: {value}")
    return tuple(int(part) for part in match.groups())


def update_payload(check_remote=False):
    result = {
        "current_version": APP_VERSION,
        "repository": GITHUB_REPOSITORY,
        "configured": True,
        "status": "ready",
        "update_available": False,
    }
    if not check_remote:
        return result
    request = Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"NovelTranslatorStudio/{APP_VERSION}",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
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
    assets = release.get("assets", [])
    asset = next(
        (item for item in assets if isinstance(item, dict) and item.get("name") == UPDATE_ASSET_NAME),
        None,
    )
    download_url = str((asset or {}).get("browser_download_url", "")).strip()
    digest = str((asset or {}).get("digest", "")).strip().lower()
    checksum = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
    version_parts(latest)
    if download_url:
        download = urlparse(download_url)
        if download.scheme not in {"https", "http"} or not download.netloc:
            raise ValueError("Đường dẫn tải bản cập nhật không hợp lệ")
    if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("SHA-256 trong manifest không hợp lệ")
    result.update({
        "status": "update_available" if version_parts(latest) > version_parts(APP_VERSION) else "up_to_date",
        "latest_version": latest,
        "update_available": version_parts(latest) > version_parts(APP_VERSION),
        "notes": str(release.get("body", "")).strip()[:2000],
        "release_url": str(release.get("html_url", "")).strip(),
        "asset_found": bool(asset),
        "download_ready": bool(download_url and checksum),
        "download_url": download_url,
        "sha256": checksum,
    })
    return result


def validate_update_archive(path: Path, expected_version: str):
    required = {
        "NovelTranslatorStudio/app.py",
        "NovelTranslatorStudio/VERSION",
        "NovelTranslatorStudio/runtime/python.exe",
        "NovelTranslatorStudio/apply_update.ps1",
    }
    with zipfile.ZipFile(path) as archive:
        names = set()
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            item = PurePosixPath(normalized)
            if item.is_absolute() or ".." in item.parts or not item.parts or item.parts[0] != "NovelTranslatorStudio":
                raise ValueError("Gói cập nhật chứa đường dẫn không an toàn")
            names.add(normalized.rstrip("/"))
        missing = required - names
        if missing:
            raise ValueError(f"Gói cập nhật thiếu file: {', '.join(sorted(missing))}")
        version = archive.read("NovelTranslatorStudio/VERSION").decode("utf-8-sig").strip()
    if version != expected_version:
        raise ValueError(f"Phiên bản trong ZIP là {version}, không phải {expected_version}")


def prepare_update():
    if not (ROOT / "runtime" / "python.exe").is_file():
        raise ValueError("Tự động cập nhật chỉ dùng được trên bản portable")
    if not UPDATER_SOURCE.is_file():
        raise ValueError("Thiếu apply_update.ps1 trong thư mục ứng dụng")
    if any(job.get("status") == "running" for job in jobs.values()):
        raise ValueError("Hãy chờ hoặc dừng mọi tác vụ trước khi cập nhật")
    release = update_payload(True)
    if not release.get("update_available"):
        raise ValueError("Không có phiên bản mới để cập nhật")
    if not release.get("download_ready"):
        raise ValueError("Release GitHub thiếu ZIP Windows hoặc SHA-256")
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPDATE_DIR / UPDATE_ASSET_NAME
    partial = destination.with_suffix(".zip.part")
    partial.unlink(missing_ok=True)
    request = Request(
        release["download_url"],
        headers={"Accept": "application/octet-stream", "User-Agent": f"NovelTranslatorStudio/{APP_VERSION}"},
    )
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=60) as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != release["sha256"]:
        partial.unlink(missing_ok=True)
        raise ValueError("Checksum SHA-256 của bản cập nhật không khớp")
    os.replace(partial, destination)
    validate_update_archive(destination, release["latest_version"])
    updater = UPDATE_DIR / "apply_update.ps1"
    shutil.copy2(UPDATER_SOURCE, updater)
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(updater),
        "-ZipPath", str(destination),
        "-AppRoot", str(ROOT),
        "-ExpectedVersion", release["latest_version"],
        "-ServerPid", str(os.getpid()),
    ]
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(command, cwd=str(ROOT), creationflags=creation_flags)
    return {"ok": True, "version": release["latest_version"], "message": "Đã tải và xác minh. App sẽ khởi động lại để cập nhật."}


def gemini_api_keys_payload():
    try:
        keys = [line.strip() for line in GEMINI_API_KEYS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError:
        keys = []
    return {"keys": keys, "count": len(keys)}


def write_gemini_api_keys(payload: dict):
    keys = payload.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ValueError("Cần ít nhất một Gemini API key")
    if len(keys) > 100:
        raise ValueError("Chỉ được lưu tối đa 100 Gemini API key")
    cleaned = []
    for key in keys:
        key = str(key).strip()
        if not key or len(key) > 500 or any(char.isspace() for char in key):
            raise ValueError("Gemini API key không hợp lệ")
        if key not in cleaned:
            cleaned.append(key)
    temporary = GEMINI_API_KEYS_FILE.with_suffix(".tmp")
    temporary.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    os.replace(temporary, GEMINI_API_KEYS_FILE)
    return {"keys": cleaned, "count": len(cleaned)}


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def active_translation():
    with translation_guard:
        if not TRANSLATION_LOCK.exists():
            return None
        try:
            data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or data.get("controller_pid") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            data, pid = {}, 0
        if process_is_running(pid):
            return data
        TRANSLATION_LOCK.unlink(missing_ok=True)
        return None


def claim_translation(kind: str, project_name: str):
    with translation_guard:
        active = active_translation()
        if active:
            engine = str(active.get("kind", "engine khác")).upper()
            project = str(active.get("project", "truyện khác"))
            raise ValueError(
                f"{engine} đang chạy cho {project}. Hãy chờ tác vụ kết thúc."
            )
        claim_id = f"{os.getpid()}-{time.time_ns()}"
        TRANSLATION_LOCK.parent.mkdir(exist_ok=True)
        stop_file = TRANSLATION_LOCK.parent / f"{claim_id}.stop"
        stop_file.unlink(missing_ok=True)
        TRANSLATION_LOCK.write_text(
            json.dumps(
                {
                    "claim_id": claim_id,
                    "kind": kind,
                    "project": project_name,
                    "controller_pid": os.getpid(),
                    "pid": None,
                    "stop_file": str(stop_file),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return claim_id


def update_translation_pid(claim_id: str, pid: int):
    with translation_guard:
        data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
        if data.get("claim_id") == claim_id:
            data["pid"] = pid
            TRANSLATION_LOCK.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )


def release_translation(claim_id: str):
    with translation_guard:
        try:
            data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if data.get("claim_id") == claim_id:
            stop_file = Path(str(data.get("stop_file", "")))
            if stop_file.name:
                stop_file.unlink(missing_ok=True)
            TRANSLATION_LOCK.unlink(missing_ok=True)


def translation_stop_file(claim_id: str) -> Path:
    return TRANSLATION_LOCK.parent / f"{claim_id}.stop"


def terminate_process_tree(pid: int):
    if pid <= 0 or pid in {os.getpid(), os.getppid()}:
        raise ValueError("Từ chối dừng tiến trình điều khiển ứng dụng")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.kill(pid, 15)


def isolated_process_kwargs():
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def google_translate(text: str):
    text = text.strip()
    if not text:
        raise ValueError("Chưa chọn nội dung cần dịch")
    if len(text) > 5000:
        raise ValueError("Đoạn được chọn quá dài; tối đa 5.000 ký tự")
    body = urlencode(
        {"client": "gtx", "sl": "auto", "tl": "vi", "dt": "t", "q": text}
    ).encode("utf-8")
    request = Request(
        "https://translate.googleapis.com/translate_a/single",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
    translated = "".join(
        part[0] for part in (data[0] if data else []) if part and part[0]
    ).strip()
    if not translated:
        raise ValueError("Google Translate không trả về bản dịch")
    return translated


def safe_project(name: str) -> Path:
    if (
        not name
        or name in {"raw", "translated"}
        or not re.fullmatch(r"[\w .-]+", name, re.UNICODE)
    ):
        raise ValueError("Tên truyện không hợp lệ; chỉ dùng chữ, số, khoảng trắng, dấu chấm, gạch ngang hoặc gạch dưới")
    path = (LIBRARY / name).resolve()
    if LIBRARY.resolve() not in path.parents:
        raise ValueError("Invalid project path")
    return path


def validate_new_project_name(name: str) -> str:
    name = str(name).strip()
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(f"Tên truyện quá dài; tối đa {MAX_PROJECT_NAME_LENGTH} ký tự")
    if name.endswith((" ", ".")):
        raise ValueError("Tên truyện không được kết thúc bằng khoảng trắng hoặc dấu chấm")
    stem = name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
        raise ValueError("Tên truyện trùng với tên hệ thống của Windows")
    safe_project(name)
    if any(existing.casefold() == name.casefold() for existing in projects()):
        raise ValueError(f"Truyện “{name}” đã tồn tại")
    return name


def project_folders(name: str):
    project = safe_project(name)
    return project / "raw", project / "translated"


def projects():
    LIBRARY.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            p.name
            for p in LIBRARY.iterdir()
            if p.is_dir()
            and p.name not in {"raw", "translated"}
            and ((p / "raw").is_dir() or (p / "translated").is_dir())
        ],
        key=str.casefold,
    )


def safe_file(folder: Path, name: str) -> Path:
    if not re.fullmatch(r"[\w.-]+\.md", name, re.UNICODE):
        raise ValueError("Tên chương không hợp lệ")
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents:
        raise ValueError("Đường dẫn không hợp lệ")
    return path


def safe_image(project_name: str, name: str) -> Path:
    if not re.fullmatch(r"[\w.-]+\.(?:jpg|jpeg|png|gif|webp|svg)", name, re.IGNORECASE):
        raise ValueError("Invalid image name")
    folder = safe_project(project_name) / "image"
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents:
        raise ValueError("Invalid image path")
    return path


def chapter_images(project_name: str, text: str):
    names = re.findall(r"!\[[^\]]*\]\((?:\.\./)?image/([\w.-]+)\)", text)
    local = [
        {
            "id": Path(name).stem,
            "url": f"/api/image/{quote(name)}?project={quote(project_name)}",
        }
        for name in names
        if safe_image(project_name, name).exists()
    ]
    remote = [
        {"id": f"remote-{i + 1}", "url": url}
        for i, url in enumerate(
            re.findall(
                r"\[img(?:=[^\]]+)?\](https?://[^\[]+)\[/img\]", text, re.IGNORECASE
            )
        )
    ]
    return local + remote


def chapters(project_name: str):
    raw, translated = project_folders(project_name)
    raw.mkdir(parents=True, exist_ok=True)
    translated.mkdir(parents=True, exist_ok=True)
    names = sorted(
        {p.name for p in raw.glob("*.md")} | {p.name for p in translated.glob("*.md")},
        key=chapter_key,
    )
    items = []
    for name in names:
        title_path = translated / name if (translated / name).exists() else raw / name
        metric_path = raw / name if (raw / name).exists() else translated / name
        metric = text_metric(metric_path)
        items.append(
            {
                "name": name,
                "id": Path(name).stem,
                "title": chapter_title(title_path),
                "raw": (raw / name).exists(),
                "translated": (translated / name).exists(),
                "words": metric["count"],
                "word_unit": metric["unit"],
            }
        )
    return items


def chapter_title(path: Path) -> str:
    try:
        for line in read_live_utf8(path).splitlines():
            title = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
            if not title:
                continue
            return title or path.stem
    except OSError:
        pass
    return path.stem


def chapter_key(name: str):
    nums = re.findall(r"\d+", name)
    return tuple(map(int, nums)) if nums else (10**9, name)


def read_live_utf8(path: Path) -> str:
    """Read a file that another translation process may currently be rewriting."""
    data = b""
    for attempt in range(4):
        data = path.read_bytes()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            if attempt < 3:
                time.sleep(0.05)
    return data.decode("utf-8", errors="replace")


def text_metric(path: Path) -> dict:
    try:
        text = read_live_utf8(path)
    except OSError:
        return {"count": 0, "unit": "từ"}
    clean = re.sub(r"\[img\][\s\S]*?\[/img\]", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"^[#>\-+*]+\s*", " ", clean, flags=re.MULTILINE)
    clean = re.sub(r"[*_~`]+", " ", clean)
    if re.search(r"[\u3400-\u9fff\u3040-\u30ff]", clean):
        return {"count": sum(char.isalnum() for char in clean), "unit": "ký tự"}
    return {
        "count": len(re.findall(r"[^\W_]+", clean, flags=re.UNICODE)),
        "unit": "từ",
    }


def word_count(path: Path) -> int:
    return text_metric(path)["count"]


def review_data(project_name: str, source: str):
    project = safe_project(project_name)
    if not re.fullmatch(r"review(?:_[\w-]+)?\.yaml", source):
        raise ValueError("Invalid review source")
    path = (project / source).resolve()
    if project.resolve() not in path.parents or not path.exists():
        raise ValueError("Review source not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return []
    items = []
    for chapter_id, value in data.items():
        if not isinstance(value, dict):
            continue
        items.append(
            {
                "chapter_id": str(chapter_id),
                "chapter_number": value.get("chapter_number"),
                "score": value.get("score"),
                "issue_count": value.get("issue_count", len(value.get("issues") or [])),
                "summary": value.get("summary", ""),
                "issues": value.get("issues") or [],
            }
        )
    return sorted(
        items, key=lambda x: (x["chapter_number"] is None, x["chapter_number"] or 0)
    )


def context_data(project_name: str):
    path = safe_project(project_name) / "context.yaml"
    if not path.exists():
        return {"index": 0, "glossary": [], "style_notes": "", "raw_yaml": ""}
    raw_yaml = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("context.yaml không hợp lệ")

    glossary = []
    for line in str(data.get("glossary", "")).splitlines():
        source, separator, target = line.partition("=")
        if separator and source.strip() and target.strip():
            glossary.append({"source": source.strip(), "target": target.strip()})
    return {
        "index": data.get("index", 0),
        "glossary": glossary,
        "style_notes": str(data.get("style_notes", "")).strip(),
        "raw_yaml": raw_yaml,
    }


def characters_data(project_name: str):
    path = safe_project(project_name) / "characters.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    names = re.findall(r"(?m)^##\s+(.+?)\s*$", content)
    return {
        "content": content,
        "exists": path.exists(),
        "count": len(names),
        "backup": path.with_name(path.name + ".bak").exists(),
        "updated_at": path.stat().st_mtime if path.exists() else None,
    }


def pronouns_data(project_name: str):
    path = safe_project(project_name) / "pronouns.yaml"
    raw_yaml = path.read_text(encoding="utf-8") if path.exists() else ""
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("pronouns.yaml không hợp lệ")
    pairs = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        timeline = [item for item in value.get("timeline", []) if isinstance(item, dict)]
        timeline.sort(key=lambda item: item.get("chapter_number", 0))
        latest = timeline[-1] if timeline else {}
        previous = timeline[-2] if len(timeline) > 1 else {}
        changed = bool(
            previous
            and (
                previous.get("speaker_self") != latest.get("speaker_self")
                or previous.get("speaker_to_listener") != latest.get("speaker_to_listener")
            )
        )
        pairs.append(
            {
                "key": str(key),
                "characters": [str(item) for item in value.get("characters", [])[:2]],
                "timeline": timeline,
                "latest": latest,
                "locked": bool(value.get("locked", False)),
                "changed": changed,
            }
        )
    pairs.sort(
        key=lambda item: item["latest"].get("chapter_number", 0), reverse=True
    )
    return {
        "pairs": pairs,
        "count": len(pairs),
        "locked_count": sum(item["locked"] for item in pairs),
        "exists": path.exists(),
        "raw_yaml": raw_yaml,
    }


def save_pronouns(project_name: str, payload: dict):
    path = safe_project(project_name) / "pronouns.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("pronouns.yaml không hợp lệ")
    key = str(payload.get("key", "")).strip()
    if not key or key not in data or not isinstance(data[key], dict):
        raise ValueError("Không tìm thấy cặp xưng hô")
    if payload.get("action") == "delete":
        del data[key]
    else:
        pair = data[key]
        timeline = pair.get("timeline", [])
        if not isinstance(timeline, list) or not timeline:
            raise ValueError("Cặp xưng hô chưa có lịch sử để chỉnh sửa")
        latest_entry = max(
            (
                (index, item)
                for index, item in enumerate(timeline)
                if isinstance(item, dict)
            ),
            key=lambda entry: (entry[1].get("chapter_number", 0), entry[0]),
            default=None,
        )
        if latest_entry is None:
            raise ValueError("Bản ghi xưng hô gần nhất không hợp lệ")
        latest = latest_entry[1]
        fields = {
            "speaker_self": str(payload.get("speaker_self", "")).strip(),
            "speaker_to_listener": str(payload.get("speaker_to_listener", "")).strip(),
            "relationship_status": str(payload.get("relationship_status", "")).strip(),
            "emotional_tone": str(payload.get("emotional_tone", "")).strip(),
        }
        if not fields["speaker_self"] or not fields["speaker_to_listener"]:
            raise ValueError("Cách tự xưng và gọi đối phương không được để trống")
        if any(len(value) > 300 for value in fields.values()):
            raise ValueError("Nội dung quy tắc xưng hô quá dài")
        latest.update(fields)
        latest["source"] = "manual"
        pair["locked"] = bool(payload.get("locked", False))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(temporary, path)
    return pronouns_data(project_name)


def publishing_data(project_name: str):
    path = safe_project(project_name) / "publishing.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    hako = data.get("hako", {}) if isinstance(data, dict) else {}
    books = hako.get("books", []) if isinstance(hako, dict) else []
    normalized = []
    if isinstance(books, list):
        for book in books:
            if not isinstance(book, dict):
                continue
            start = book.get("volume", book.get("from_volume"))
            end = book.get("volume", book.get("to_volume", start))
            try:
                start, end = int(start), int(end)
            except (TypeError, ValueError):
                continue
            for volume in range(start, end + 1):
                normalized.append(
                    {
                        "label": str(book.get("label", "")).strip(),
                        "book_id": str(book.get("book_id", "")).strip(),
                        "volume": volume,
                    }
                )
    return {"books": normalized, "exists": path.exists()}


def save_publishing(project_name: str, payload: dict):
    path = safe_project(project_name) / "publishing.yaml"
    incoming = payload.get("books")
    if not isinstance(incoming, list) or len(incoming) > 100:
        raise ValueError("Danh sách book Hako không hợp lệ")
    books = []
    occupied = {}
    for index, item in enumerate(incoming, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Book {index} không hợp lệ")
        label = str(item.get("label", "")).strip()
        book_id = str(item.get("book_id", "")).strip()
        link_match = re.search(r"(?:book=)?(\d+)(?:\D*)$", book_id)
        if link_match:
            book_id = link_match.group(1)
        try:
            volume = int(item.get("volume"))
        except (TypeError, ValueError):
            raise ValueError(f"Volume của book {index} phải là số nguyên") from None
        if (
            len(label) > 100
            or not book_id.isdigit()
            or len(book_id) > 20
        ):
            raise ValueError(f"Book ID tại dòng {index} không hợp lệ")
        if volume < 0 or volume > 10000:
            raise ValueError(f"Volume tại dòng {index} không hợp lệ")
        label = label or f"Volume {volume}"
        if volume in occupied:
            raise ValueError(
                f"Volume {volume} đang được gán cho cả “{occupied[volume]}” và “{label}”"
            )
        occupied[volume] = label
        books.append(
            {
                "label": label,
                "book_id": book_id,
                "volume": volume,
            }
        )
    data = {"hako": {"books": sorted(books, key=lambda x: x["volume"])}}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(temporary, path)
    return publishing_data(project_name)


def save_characters(project_name: str, payload: dict):
    path = safe_project(project_name) / "characters.md"
    content = str(payload.get("content", "")).replace("\r\n", "\n")
    if "\x00" in content or len(content.encode("utf-8")) > 5 * 1024 * 1024:
        raise ValueError("Hồ sơ nhân vật không hợp lệ hoặc vượt quá 5 MB")
    if path.exists() and path.stat().st_size and not content.strip():
        raise ValueError("Không thể vô tình xóa sạch hồ sơ nhân vật")
    if content and not content.endswith("\n"):
        content += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
    return characters_data(project_name)


def task_stop_file(kind: str) -> Path:
    safe_kind = re.sub(r"[^a-z0-9_-]", "", kind.lower())
    return ROOT / ".runtime" / f"{safe_kind}.stop"


def write_context_safely(path: Path, data: dict):
    content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    checked = yaml.safe_load(content)
    if not isinstance(checked, dict):
        raise ValueError("Context sau khi lưu không hợp lệ")
    temporary = path.with_name(path.name + ".tmp")
    backup = path.with_name(path.name + ".bak")
    temporary.write_text(content, encoding="utf-8")
    if path.exists():
        shutil.copy2(path, backup)
    os.replace(temporary, path)


def save_context(project_name: str, payload: dict):
    path = safe_project(project_name) / "context.yaml"
    if "context_fields" in payload:
        fields = payload.get("context_fields")
        if not isinstance(fields, dict):
            raise ValueError("Dữ liệu context không hợp lệ")
        try:
            index = int(fields.get("index", 0))
        except (TypeError, ValueError):
            raise ValueError("Tiến độ chương phải là số nguyên") from None
        raw_count = len(list((path.parent / "raw").glob("*.md")))
        if index < 0 or (raw_count and index > raw_count):
            raise ValueError(f"Tiến độ chương phải nằm trong khoảng 0–{raw_count}")

        glossary_lines = []
        invalid = []
        for number, line in enumerate(str(fields.get("glossary", "")).splitlines(), 1):
            if not line.strip():
                continue
            source, separator, target = line.partition("=")
            if not separator or not source.strip() or not target.strip():
                invalid.append(number)
            else:
                glossary_lines.append(f"{source.strip()} = {target.strip()}")
        if invalid:
            lines = ", ".join(map(str, invalid[:10]))
            raise ValueError(f"Glossary sai định dạng Raw = Dịch tại dòng: {lines}")

        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        data = data or {}
        if not isinstance(data, dict):
            raise ValueError("context.yaml hiện tại không hợp lệ")
        if data.get("glossary") and not glossary_lines:
            raise ValueError("Không thể xóa toàn bộ glossary trong một lần lưu")
        data["index"] = index
        data["glossary"] = "\n".join(glossary_lines)
        data["style_notes"] = str(fields.get("style_notes", "")).strip()
        write_context_safely(path, data)
        result = context_data(project_name)
        result["backup"] = path.with_name(path.name + ".bak").exists()
        return result

    if "raw_yaml" in payload:
        raw_yaml = str(payload.get("raw_yaml", ""))
        data = yaml.safe_load(raw_yaml) or {}
        if not isinstance(data, dict):
            raise ValueError("context.yaml phải có cấu trúc key: value")
        write_context_safely(path, data)
        return context_data(project_name)

    glossary_text = str(payload.get("glossary_text", ""))
    incoming = []
    invalid = []
    for number, line in enumerate(glossary_text.splitlines(), 1):
        if not line.strip():
            continue
        source, separator, target = line.partition("=")
        if not separator or not source.strip() or not target.strip():
            invalid.append(number)
        else:
            incoming.append((source.strip(), target.strip()))
    if invalid:
        lines = ", ".join(map(str, invalid[:10]))
        raise ValueError(f"Glossary sai định dạng Raw = Dịch tại dòng: {lines}")
    if not incoming:
        raise ValueError("Chưa có thuật ngữ hợp lệ để nạp")

    raw_yaml = path.read_text(encoding="utf-8") if path.exists() else ""
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("context.yaml không hợp lệ")
    merged = {}
    for line in str(data.get("glossary", "")).splitlines():
        source, separator, target = line.partition("=")
        if separator and source.strip() and target.strip():
            merged[source.strip()] = target.strip()
    for source, target in incoming:
        merged[source] = target
    data["glossary"] = "\n".join(f"{source} = {target}" for source, target in merged.items())
    write_context_safely(path, data)
    result = context_data(project_name)
    result["imported"] = len(incoming)
    return result


def stream_process_output(process: subprocess.Popen, job_key: str) -> str:
    """Publish child-process output to the web console as each line arrives."""
    output = ""
    if process.stdout is not None:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            if line.startswith("@@NOVEL_STREAM@@"):
                try:
                    event = json.loads(line[len("@@NOVEL_STREAM@@") :])
                    current = jobs.get(job_key)
                    if current is not None and isinstance(event, dict):
                        sequence = int(current.get("stream_sequence", 0)) + 1
                        current["stream_sequence"] = sequence
                        event["sequence"] = sequence
                        live_events = job_stream_events.setdefault(job_key, [])
                        live_events.append(dict(event))
                        del live_events[:-1000]
                        events = current.setdefault("stream_events", [])
                        if (
                            events
                            and event.get("type") == "translation_snapshot"
                            and events[-1].get("type") == "translation_snapshot"
                            and events[-1].get("chapter") == event.get("chapter")
                        ):
                            events[-1] = event
                        else:
                            events.append(event)
                            del events[:-300]
                    continue
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass
            output = (output + line)[-12000:]
            current = jobs.get(job_key)
            if current is not None:
                current["output"] = output.rstrip()
        process.stdout.close()
    process.wait()
    return output.strip()


def prepare_manual_prompt(project_name: str):
    project = safe_project(project_name)
    if not project.is_dir():
        raise ValueError(f"Không tìm thấy truyện “{project_name}”")
    if active_translation():
        raise ValueError("Hãy chờ tác vụ dịch hiện tại kết thúc trước khi tạo prompt")

    cache = project / ".manual_prompt.json"
    cache.unlink(missing_ok=True)
    config = {**saved_settings(), "manual_result": "", "skip_login_prompt": True}
    process = subprocess.run(
        [sys.executable, "-u", str(PIPELINES["manual"])],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "NOVEL_PROJECT": project_name,
            "NOVEL_WEB_MODE": "1",
            "NOVEL_WEB_CONFIG": json.dumps(config, ensure_ascii=False),
        },
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "").strip()[-1500:]
        raise ValueError(detail or "Không thể tạo prompt dịch thủ công")
    if not cache.exists():
        raise ValueError("Không còn chương chưa dịch để tạo prompt")

    data = json.loads(cache.read_text(encoding="utf-8"))
    chapter = str(data.get("chapter", ""))
    prompt = str(data.get("prompt", ""))
    raw, translated = project_folders(project_name)
    safe_file(raw, chapter)
    if (translated / chapter).exists():
        raise ValueError("Chương vừa chọn đã có bản dịch. Hãy tải lại danh sách chương")
    if not prompt.strip():
        raise ValueError("Prompt dịch thủ công đang trống")
    return {
        "chapter": chapter,
        "title": str(data.get("title", Path(chapter).stem)),
        "prompt": prompt,
    }


def run_job(
    kind: str,
    project_name: str,
    config: dict | None = None,
    translation_claim: str | None = None,
):
    script = PIPELINES[kind]
    job_stream_events[kind] = []
    task_config = dict(config or {})
    if kind == "manual":
        manual_result = str(task_config.pop("manual_result", ""))
        project = safe_project(project_name)
        result_path = project / ".manual_result.txt"
        temporary = result_path.with_name(result_path.name + ".tmp")
        temporary.write_text(manual_result, encoding="utf-8")
        os.replace(temporary, result_path)
        task_config["manual_result_ready"] = True
    effective_config = {**saved_settings(), **task_config}
    stop_file = task_stop_file(kind)
    stop_file.parent.mkdir(exist_ok=True)
    stop_file.unlink(missing_ok=True)
    jobs[kind] = {
        "status": "running",
        "output": "Đang khởi động…",
        "project": project_name,
        "streaming": kind == "v1-interactions",
        "claim_id": translation_claim,
        "stream_events": [],
        "stream_sequence": 0,
    }
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(script)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "NOVEL_PROJECT": project_name,
                "NOVEL_WEB_MODE": "1",
                "NOVEL_WEB_CONFIG": json.dumps(effective_config, ensure_ascii=False),
                "NOVEL_STOP_FILE": str(translation_stop_file(translation_claim))
                if translation_claim else str(stop_file),
            },
            **isolated_process_kwargs(),
        )
        job_processes[kind] = process
        if translation_claim:
            update_translation_pid(translation_claim, process.pid)
        output = stream_process_output(process, kind)
        cancelled = jobs.get(kind, {}).get("cancel_mode") == "immediate"
        stream_state = jobs.get(kind, {})
        jobs[kind] = {
            "status": "cancelled"
            if cancelled
            else ("done" if process.returncode == 0 else "error"),
            "output": output,
            "stream_events": stream_state.get("stream_events", []),
            "stream_sequence": stream_state.get("stream_sequence", 0),
        }
    except Exception as exc:
        stream_state = jobs.get(kind, {})
        jobs[kind] = {
            "status": "error",
            "output": str(exc),
            "stream_events": stream_state.get("stream_events", []),
            "stream_sequence": stream_state.get("stream_sequence", 0),
        }
    finally:
        job_processes.pop(kind, None)
        stop_file.unlink(missing_ok=True)
        if translation_claim:
            release_translation(translation_claim)


def retranslate_job(
    engine: str,
    project_name: str,
    chapter_name: str,
    translation_claim: str,
):
    job_key = "retranslate"
    job_stream_events[job_key] = []
    _, translated = project_folders(project_name)
    target = safe_file(translated, chapter_name)
    backup = target.with_suffix(target.suffix + ".web-backup")
    effective_config = {
        **saved_settings(),
        "run_until_complete": False,
        "skip_login_prompt": True,
        "target_chapter": chapter_name,
    }
    jobs[job_key] = {
        "status": "running",
        "output": f"Retranslating {chapter_name} with {engine.upper()}...",
        "project": project_name,
        "streaming": engine == "v1-interactions",
        "claim_id": translation_claim,
        "stream_events": [],
        "stream_sequence": 0,
    }
    try:
        if backup.exists():
            backup.unlink()
        if target.exists():
            target.replace(backup)
        process = subprocess.Popen(
            [sys.executable, "-u", str(PIPELINES[engine])],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "NOVEL_PROJECT": project_name,
                "NOVEL_WEB_MODE": "1",
                "NOVEL_WEB_CONFIG": json.dumps(effective_config, ensure_ascii=False),
                "NOVEL_STOP_FILE": str(translation_stop_file(translation_claim)),
            },
            **isolated_process_kwargs(),
        )
        job_processes[job_key] = process
        update_translation_pid(translation_claim, process.pid)
        output = stream_process_output(process, job_key)
        cancelled = jobs.get(job_key, {}).get("cancel_mode") == "immediate"
        if cancelled or process.returncode != 0 or not target.exists():
            if backup.exists():
                backup.replace(target)
            stream_state = jobs.get(job_key, {})
            jobs[job_key] = {
                "status": "cancelled" if cancelled else "error",
                "output": output or "Translation did not create an output file",
                "stream_events": stream_state.get("stream_events", []),
                "stream_sequence": stream_state.get("stream_sequence", 0),
            }
            return
        if backup.exists():
            backup.unlink()
        stream_state = jobs.get(job_key, {})
        jobs[job_key] = {
            "status": "done",
            "output": output,
            "stream_events": stream_state.get("stream_events", []),
            "stream_sequence": stream_state.get("stream_sequence", 0),
        }
    except Exception as exc:
        if backup.exists():
            if target.exists():
                target.unlink()
            backup.replace(target)
        stream_state = jobs.get(job_key, {})
        jobs[job_key] = {
            "status": "error",
            "output": str(exc),
            "stream_events": stream_state.get("stream_events", []),
            "stream_sequence": stream_state.get("stream_sequence", 0),
        }
    finally:
        job_processes.pop(job_key, None)
        release_translation(translation_claim)


def lan_configuration():
    settings = saved_settings()
    enabled = settings.get("lan_enabled") == "on"
    pin = str(settings.get("lan_pin", ""))
    return enabled and bool(re.fullmatch(r"\d{6,12}", pin)), pin


def local_network_ip():
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("8.8.8.8", 80))
        return connection.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        connection.close()


LAN_LOGIN_HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Novel Translator Studio</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100dvh;display:grid;place-items:center;padding:20px;background:#101412;color:#e9efeb;font-family:Segoe UI,Arial,sans-serif}.card{width:min(100%,390px);padding:28px;border:1px solid #2b332f;border-radius:18px;background:#171c19;box-shadow:0 20px 70px #0008}.mark{display:grid;place-items:center;width:46px;height:46px;border-radius:13px;background:#d6f064;color:#18211e;font-size:22px;font-weight:800}h1{margin:22px 0 8px;font-size:24px}p{margin:0 0 22px;color:#a8b2ad;line-height:1.55}label{display:grid;gap:8px;font-size:13px;font-weight:700}input{width:100%;padding:14px;border:1px solid #36413b;border-radius:11px;background:#0f1311;color:#fff;font-size:20px;letter-spacing:.25em;text-align:center;outline:0}input:focus{border-color:#55b89d}button{width:100%;margin-top:14px;padding:13px;border:0;border-radius:11px;background:#177e68;color:#fff;font-weight:750}small{display:block;min-height:20px;margin-top:12px;color:#f08b7c;text-align:center}</style></head><body><main class="card"><div class="mark">N</div><h1>Truy cập từ điện thoại</h1><p>Nhập mã PIN đang hiển thị trong Cài đặt trên máy tính.</p><form><label>Mã PIN<input name="pin" inputmode="numeric" pattern="[0-9]{6,12}" maxlength="12" autocomplete="one-time-code" required></label><button>Đăng nhập</button><small></small></form></main><script>
const f=document.querySelector('form'),m=document.querySelector('small');f.onsubmit=async e=>{e.preventDefault();m.textContent='';const b=f.querySelector('button');b.disabled=true;try{const r=await fetch('/api/lan/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:new FormData(f).get('pin')})});const d=await r.json();if(!r.ok)throw Error(d.error||'Không đăng nhập được');location.reload()}catch(e){m.textContent=e.message}finally{b.disabled=false}};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def json_response(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def stream_job_events(self, job_key: str, after: int):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last_sequence = after
        last_ping = time.monotonic()
        try:
            while True:
                pending = [
                    event
                    for event in job_stream_events.get(job_key, [])
                    if int(event.get("sequence", 0)) > last_sequence
                ]
                for event in pending:
                    payload = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    last_sequence = int(event.get("sequence", last_sequence))
                if pending:
                    self.wfile.flush()
                job = jobs.get(job_key, {})
                if job.get("status") in {"done", "error", "cancelled"} and not pending:
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                    return
                if time.monotonic() - last_ping >= 10:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_ping = time.monotonic()
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def is_loopback(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def lan_authorized(self):
        if self.is_loopback():
            return True
        configured, _pin = lan_configuration()
        if not configured:
            return False
        cookie = self.headers.get("Cookie", "")
        token = next(
            (
                part.split("=", 1)[1]
                for part in cookie.split(";")
                if part.strip().startswith("nts_lan_session=")
            ),
            "",
        ).strip()
        return token in lan_sessions

    def require_lan_authorization(self, api_request=False):
        if self.lan_authorized():
            return False
        if api_request:
            self.json_response(
                {"error": "Điện thoại chưa đăng nhập mã PIN LAN."},
                HTTPStatus.UNAUTHORIZED,
            )
        else:
            body = LAN_LOGIN_HTML.encode("utf-8")
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if self.require_lan_authorization(path.startswith("/api/")):
            return
        project = query.get("project", [""])[0]
        if path == "/api/projects":
            return self.json_response({"items": projects()})
        if path == "/api/settings":
            return self.json_response(settings_payload())
        if path == "/api/update":
            try:
                return self.json_response(update_payload(query.get("check", ["0"])[0] == "1"))
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/health":
            return self.json_response({"ok": True, "version": APP_VERSION})
        if path == "/api/lan/status":
            configured, pin = lan_configuration()
            return self.json_response(
                {
                    "configured": configured,
                    "active": HOST == "0.0.0.0",
                    "url": f"http://{local_network_ip()}:{PORT}" if configured else "",
                    "pin": pin if self.is_loopback() else "",
                }
            )
        if path == "/api/publishing":
            try:
                return self.json_response(publishing_data(project))
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys":
            return self.json_response(gemini_api_keys_payload())
        if path == "/api/reviews":
            try:
                project_path = safe_project(project)
                sources = sorted(
                    p.name for p in project_path.glob("review*.yaml") if p.is_file()
                )
                source = query.get("source", [sources[0] if sources else ""])[0]
                items = review_data(project, source) if source else []
                return self.json_response(
                    {"sources": sources, "source": source, "items": items}
                )
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/context":
            try:
                return self.json_response(context_data(project))
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/characters":
            try:
                return self.json_response(characters_data(project))
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/pronouns":
            try:
                return self.json_response(pronouns_data(project))
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/chapters":
            try:
                items = chapters(project)
            except ValueError as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return self.json_response(
                {
                    "items": items,
                    "total": len(items),
                    "translated": sum(x["translated"] for x in items),
                }
            )
        if path.startswith("/api/chapter/"):
            name = unquote(path.rsplit("/", 1)[-1])
            try:
                raw, translated = project_folders(project)
                raw_path, trans_path = safe_file(raw, name), safe_file(translated, name)
                raw_text = read_live_utf8(raw_path) if raw_path.exists() else ""
                return self.json_response(
                    {
                        "name": name,
                        "raw": raw_text,
                        "translated": read_live_utf8(trans_path)
                        if trans_path.exists()
                        else "",
                        "images": chapter_images(project, raw_text),
                    }
                )
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path.startswith("/api/job/"):
            return self.json_response(
                jobs.get(path.rsplit("/", 1)[-1], {"status": "idle", "output": ""})
            )
        if path == "/api/jobs/active":
            return self.json_response(
                {
                    "items": [
                        {"kind": kind, **job}
                        for kind, job in jobs.items()
                        if job.get("status") == "running"
                    ]
                }
            )
        if path.startswith("/api/job-stream/"):
            job_key = unquote(path.rsplit("/", 1)[-1])
            if job_key not in PIPELINES and job_key != "retranslate":
                return self.json_response({"error": "Unknown job"}, HTTPStatus.NOT_FOUND)
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
            except ValueError:
                after = 0
            return self.stream_job_events(job_key, after)
        if path.startswith("/api/image/"):
            try:
                target = safe_image(project, unquote(path.rsplit("/", 1)[-1]))
                if not target.is_file():
                    raise ValueError("Image not found")
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    mimetypes.guess_type(target.name)[0] or "application/octet-stream",
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(data)
                return
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        return self.static(path)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/lan/login":
                return self.lan_login()
            if self.require_lan_authorization(True):
                return
            return self._do_POST()
        except Exception as exc:
            traceback.print_exc()
            try:
                return self.json_response(
                    {"error": f"Server xử lý yêu cầu thất bại: {exc}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            except (BrokenPipeError, ConnectionResetError, OSError):
                return None

    def lan_login(self):
        configured, expected_pin = lan_configuration()
        if not configured:
            return self.json_response(
                {"error": "Truy cập LAN chưa được bật."}, HTTPStatus.FORBIDDEN
            )
        address = self.client_address[0]
        now = time.time()
        attempts = [stamp for stamp in lan_login_attempts.get(address, []) if now - stamp < 300]
        if len(attempts) >= 10:
            return self.json_response(
                {"error": "Đã nhập sai quá nhiều lần. Hãy chờ 5 phút."},
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        try:
            supplied_pin = str(self.body().get("pin", "")).strip()
        except (ValueError, json.JSONDecodeError):
            supplied_pin = ""
        if not secrets.compare_digest(supplied_pin, expected_pin):
            attempts.append(now)
            lan_login_attempts[address] = attempts
            return self.json_response(
                {"error": "Mã PIN không đúng."}, HTTPStatus.UNAUTHORIZED
            )
        lan_login_attempts.pop(address, None)
        token = secrets.token_urlsafe(32)
        lan_sessions.add(token)
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Set-Cookie", f"nts_lan_session={token}; Path=/; HttpOnly; SameSite=Strict"
        )
        self.end_headers()
        self.wfile.write(body)

    def _do_POST(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        project = query.get("project", [""])[0]
        if path == "/api/projects":
            project_path = None
            created_project = False
            try:
                name = validate_new_project_name(query.get("name", [""])[0])
                volume = int(query.get("volume", ["1"])[0])
                segment_limit = int(query.get("segment_limit", ["5000"])[0])
                source_format = query.get("format", ["epub"])[0].lower()
                project_path = safe_project(name)
                if project_path.exists():
                    raise ValueError(f"Truyện “{name}” đã tồn tại")
                if volume < 0:
                    raise ValueError("Volume không hợp lệ")
                if source_format not in {"epub", "txt"}:
                    raise ValueError("Chỉ hỗ trợ file EPUB hoặc TXT")
                if not 500 <= segment_limit <= 50000:
                    raise ValueError("Giới hạn segment phải từ 500 đến 50.000")
                length = int(self.headers.get("Content-Length", 0))
                if not length or length > 300 * 1024 * 1024:
                    raise ValueError("File trống hoặc vượt quá 300 MB")
                project_path.mkdir(parents=True)
                created_project = True
                (project_path / "translated").mkdir()
                upload = project_path / f".import.{source_format}"
                upload.write_bytes(self.rfile.read(length))
                from split.chapter_splitter_novelpia_md import split_epub_to_md, split_txt_to_md

                splitter = split_epub_to_md if source_format == "epub" else split_txt_to_md
                result = splitter(
                    str(upload), volume, str(ROOT), project_dir=str(project_path),
                    segment_limit=segment_limit, return_details=True,
                )
                upload.unlink(missing_ok=True)
                if result["segments"] <= 0:
                    raise ValueError(f"Không tách được chương nào từ {source_format.upper()}")
                return self.json_response(
                    {"ok": True, "project": name, **result}, HTTPStatus.CREATED
                )
            except Exception as exc:
                if created_project and project_path is not None and project_path.exists():
                    resolved_project = project_path.resolve()
                    resolved_library = LIBRARY.resolve()
                    if resolved_project.parent == resolved_library:
                        shutil.rmtree(resolved_project)
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path.startswith("/api/chapter/"):
            name = unquote(path.rsplit("/", 1)[-1])
            try:
                _, translated = project_folders(project)
                target = safe_file(translated, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    str(self.body().get("translated", "")), encoding="utf-8"
                )
                return self.json_response({"ok": True, "words": word_count(target)})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/context":
            try:
                return self.json_response(save_context(project, self.body()))
            except Exception as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/characters":
            try:
                return self.json_response(save_characters(project, self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/pronouns":
            try:
                return self.json_response(save_pronouns(project, self.body()))
            except (ValueError, OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/settings":
            try:
                return self.json_response(write_settings(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/update":
            try:
                result = prepare_update()
                threading.Timer(0.8, self.server.shutdown).start()
                return self.json_response(result)
            except (ValueError, OSError, zipfile.BadZipFile) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/publishing":
            try:
                return self.json_response(save_publishing(project, self.body()))
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys":
            try:
                return self.json_response(write_gemini_api_keys(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/manual-prompt":
            try:
                return self.json_response(prepare_manual_prompt(project))
            except (
                ValueError,
                OSError,
                json.JSONDecodeError,
                subprocess.TimeoutExpired,
            ) as exc:
                message = (
                    "Tạo prompt quá thời gian cho phép"
                    if isinstance(exc, subprocess.TimeoutExpired)
                    else str(exc)
                )
                return self.json_response({"error": message}, HTTPStatus.BAD_REQUEST)
        if path == "/api/translate-selection":
            try:
                text = str(self.body().get("text", ""))
                return self.json_response({"translated": google_translate(text)})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path.startswith("/api/run/"):
            kind = path.rsplit("/", 1)[-1]
            if kind not in PIPELINES or not PIPELINES[kind].exists():
                return self.json_response(
                    {"error": "Pipeline không tồn tại"}, HTTPStatus.NOT_FOUND
                )
            if jobs.get(kind, {}).get("status") == "running":
                return self.json_response(
                    {"error": "Pipeline đang chạy"}, HTTPStatus.CONFLICT
                )
            if kind == "review" and active_translation():
                return self.json_response(
                    {"error": "Hãy dừng hoặc chờ dịch xong trước khi Review toàn bộ"},
                    HTTPStatus.CONFLICT,
                )
            if kind in TRANSLATION_KINDS and jobs.get("review", {}).get("status") == "running":
                return self.json_response(
                    {"error": "Review toàn bộ đang chạy; hãy chờ review hoàn tất trước khi dịch"},
                    HTTPStatus.CONFLICT,
                )
            try:
                project_path = safe_project(project)
                if not project_path.is_dir():
                    raise ValueError(
                        f"Không tìm thấy truyện “{project}”. "
                        "Hãy tải lại danh sách truyện và chọn lại."
                    )
                payload = self.body()
                config = payload.get("config", {})
                if not isinstance(config, dict) or any(
                    not isinstance(key, str) or isinstance(value, (dict, list))
                    for key, value in config.items()
                ):
                    raise ValueError("Cấu hình tác vụ không hợp lệ")
                if kind == "manual":
                    target = str(config.get("target_chapter", ""))
                    result = str(config.get("manual_result", ""))
                    raw, translated = project_folders(project)
                    safe_file(raw, target)
                    if (translated / target).exists():
                        raise ValueError(
                            "Chương này đã có bản dịch. Hãy tạo lại prompt cho chương kế tiếp."
                        )
                    if not result.strip() or len(result.encode("utf-8")) > 5 * 1024 * 1024:
                        raise ValueError("Kết quả dịch thủ công đang trống hoặc vượt quá 5 MB")
            except ValueError as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            translation_claim = None
            if kind in TRANSLATION_KINDS:
                try:
                    translation_claim = claim_translation(kind, project)
                except ValueError as exc:
                    return self.json_response(
                        {"error": str(exc)}, HTTPStatus.CONFLICT
                    )
            try:
                threading.Thread(
                    target=run_job,
                    args=(kind, project, config, translation_claim),
                    daemon=True,
                ).start()
            except Exception:
                if translation_claim:
                    release_translation(translation_claim)
                raise
            return self.json_response({"ok": True}, HTTPStatus.ACCEPTED)
        if path == "/api/translation/cancel":
            try:
                mode = self.body().get("mode")
                if mode not in {"immediate", "after_current"}:
                    raise ValueError("Chế độ dừng không hợp lệ")
                active = active_translation()
                if not active:
                    raise ValueError("Không có tác vụ dịch đang chạy")
                claim_id = str(active.get("claim_id", ""))
                matching_entry = next(
                    (
                        (job_key, job)
                        for job_key, job in jobs.items()
                        if job.get("claim_id") == claim_id
                        and job.get("status") == "running"
                    ),
                    None,
                )
                matching_job = matching_entry[1] if matching_entry else None
                if mode == "after_current":
                    translation_stop_file(claim_id).touch()
                    if matching_job is not None:
                        matching_job["cancel_mode"] = mode
                else:
                    translation_stop_file(claim_id).touch()
                    if matching_job is not None:
                        matching_job["cancel_mode"] = mode
                        matching_job["output"] = "Đang hủy dịch ngay lập tức…"
                    process = (
                        job_processes.get(matching_entry[0])
                        if matching_entry else None
                    )
                    active_pid = int(active.get("pid") or 0)
                    if (
                        process is None
                        or process.poll() is not None
                        or process.pid != active_pid
                    ):
                        raise ValueError(
                            "Không xác định được đúng tiến trình dịch; server vẫn được giữ nguyên"
                        )
                    terminate_process_tree(process.pid)
                return self.json_response({"ok": True, "mode": mode})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/job/cancel":
            try:
                kind = str(self.body().get("kind", ""))
                job = jobs.get(kind)
                process = job_processes.get(kind)
                if not job or job.get("status") != "running" or process is None:
                    raise ValueError("Không có tác vụ này đang chạy")
                task_stop_file(kind).touch()
                job["cancel_mode"] = "immediate"
                job["output"] = "Đang dừng tác vụ…"
                if process.poll() is None:
                    terminate_process_tree(process.pid)
                return self.json_response({"ok": True, "kind": kind})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/retranslate":
            try:
                payload = self.body()
                engine, chapter = payload.get("engine", ""), payload.get("chapter", "")
                raw, _ = project_folders(project)
                safe_file(raw, chapter)
                if engine not in {"v1", "v1-interactions", "v2", "v3", "gpt", "gpt-api"}:
                    raise ValueError("Invalid translation engine")
                if jobs.get("retranslate", {}).get("status") == "running":
                    return self.json_response(
                        {"error": "A chapter is already being retranslated"},
                        HTTPStatus.CONFLICT,
                    )
                translation_claim = claim_translation(engine, project)
                try:
                    threading.Thread(
                        target=retranslate_job,
                        args=(engine, project, chapter, translation_claim),
                        daemon=True,
                    ).start()
                except Exception:
                    release_translation(translation_claim)
                    raise
                return self.json_response({"ok": True}, HTTPStatus.ACCEPTED)
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        self.json_response({"error": "Không tìm thấy"}, HTTPStatus.NOT_FOUND)

    def static(self, path: str):
        if path.startswith("/api/"):
            return self.json_response(
                {"error": "Không tìm thấy API"}, HTTPStatus.NOT_FOUND
            )
        rel = "index.html" if path in ("", "/") else unquote(path.lstrip("/"))
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            target = WEB / "index.html"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        )
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    lan_ready, _lan_pin = lan_configuration()
    HOST = "0.0.0.0" if lan_ready else "127.0.0.1"
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Novel Translator is running at {url} - press Ctrl+C to stop")
    if lan_ready:
        print(f"Mobile LAN access: http://{local_network_ip()}:{PORT}")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
