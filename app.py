from __future__ import annotations

import json
import hashlib
import html as html_lib
import difflib
import io
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
import unicodedata
import uuid
import webbrowser
import zipfile
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml
from PIL import Image, ImageOps

from cores.data_paths import (
    DATA_DIR,
    GEMINI_API_KEYS_FILE,
    GEMINI_API_KEY_STATE_FILE,
    R19_WORDS_FILE,
    ensure_user_data_migrated,
)

try:
    import boto3
except ImportError:
    boto3 = None

from cores.translation_prompts import (
    DEFAULT_POLISH_ROLE,
    DEFAULT_POLISH_TASK,
    DEFAULT_ROLE,
    DEFAULT_TASK,
    POLISH_PROMPT_PRESETS,
    PROMPT_PRESETS,
    polish_prompt_presets_payload,
    prompt_presets_payload,
)

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
    "hako-edit": ROOT / "up" / "edit_hako.py",
}
jobs: dict[str, dict] = {}
job_processes: dict[str, subprocess.Popen] = {}
job_stream_events: dict[str, list[dict]] = {}
chapter_import_previews: dict[str, dict] = {}
TRANSLATION_KINDS = {"v1", "v1-interactions", "v2", "v3", "gpt", "gpt-api", "manual"}
TRANSLATION_LOCK = ROOT / ".runtime" / "translation.lock"
translation_guard = threading.RLock()
lan_sessions: set[str] = set()
lan_login_attempts: dict[str, list[float]] = {}

SETTINGS_FILE = ROOT / ".runtime" / "settings.json"
ensure_user_data_migrated()
UI_PREFERENCES_FILE = DATA_DIR / "ui_preferences.json"
DEFAULT_PINNED_SIDEBAR = [
    "workspace", "chapters", "pipeline", "terminology", "characters", "help",
]
SIDEBAR_FEATURES = set(DEFAULT_PINNED_SIDEBAR) | {
    "sharing", "hakoEdit", "pronouns", "r19", "ai-log", "settings",
}
FIXED_SIDEBAR_FEATURES = {"settings"}


def ui_preferences_data():
    try:
        data = json.loads(UI_PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    sidebar = data.get("sidebar", {}) if isinstance(data, dict) else {}
    pinned = sidebar.get("pinned") if isinstance(sidebar, dict) else None
    if not isinstance(pinned, list):
        return {"sidebar": {"pinned": list(DEFAULT_PINNED_SIDEBAR)}}
    cleaned = []
    for item in pinned:
        item = str(item)
        if item in SIDEBAR_FEATURES and item not in FIXED_SIDEBAR_FEATURES and item not in cleaned:
            cleaned.append(item)
    return {"sidebar": {"pinned": cleaned}}


def write_ui_preferences(payload):
    sidebar = payload.get("sidebar", {}) if isinstance(payload, dict) else {}
    pinned = sidebar.get("pinned") if isinstance(sidebar, dict) else None
    if not isinstance(pinned, list):
        raise ValueError("Danh sách chức năng đã ghim không hợp lệ")
    cleaned = []
    for item in pinned:
        item = str(item)
        if item not in SIDEBAR_FEATURES:
            raise ValueError(f"Chức năng không hợp lệ: {item}")
        if item not in FIXED_SIDEBAR_FEATURES and item not in cleaned:
            cleaned.append(item)
    UI_PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = UI_PREFERENCES_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"sidebar": {"pinned": cleaned}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, UI_PREFERENCES_FILE)
    return {"sidebar": {"pinned": cleaned}}
R19_DEFAULT_WORDS_FILE = ROOT / "defaults" / "r19_words.txt"
R19_CONFIG_FILE = ROOT / ".runtime" / "r19.json"
R19_DEFAULT_MODEL = "gemini-3.5-flash-lite"
R19_DEFAULT_CONTEXT_CHAPTERS = 0
R19_DEFAULT_PROMPT_PREFIX = 'Cách để AI dịch đc prompt sau """'
DEFAULT_REVIEW_BG_CRITERIA = """1. Thiếu nội dung: chỉ báo khi một ý, hành động, hội thoại hoặc sự kiện trong bản gốc thực sự biến mất khỏi bản dịch; không báo lỗi khi bản dịch diễn đạt cô đọng nhưng vẫn đủ nghĩa.
2. Dịch sai nội dung: báo khi ý nghĩa thay đổi rõ rệt, nhầm nhân vật, sự kiện hoặc quan hệ nguyên nhân-kết quả.
3. Xưng hô: kiểm tra giới tính, vai vế, quan hệ và ngữ cảnh giao tiếp của nhân vật.
4. Phong cách và thuật ngữ: kiểm tra độ tự nhiên của tiếng Việt và tính nhất quán với glossary tham chiếu.
5. Ngoại ngữ: chỉ báo khi ký tự hoặc câu ngoại ngữ thực sự còn xuất hiện trong bản dịch; không dùng văn bản nguồn làm bằng chứng cho lỗi này.
6. Chỉ nêu lỗi khi có dẫn chứng cụ thể trong cả bản gốc và bản dịch; không suy đoán hoặc bắt lỗi khác biệt diễn đạt thuần túy."""
SETTING_DEFAULTS = {
    "link_gemini": "https://gemini.google.com/gem/fdec65ac9c69",
    "translate_model": "gemini-3.5-flash",
    "r19_model": R19_DEFAULT_MODEL,
    "polish_model": "gemini-3-flash-preview",
    "review_bg_model": "gemini-3.1-flash-lite-preview",
    "review_bg_criteria": DEFAULT_REVIEW_BG_CRITERIA,
    "pronoun_model": "gemini-3.1-flash-lite-preview",
    "review_model": "gemini-3.1-flash-lite-preview",
    "context_model": "gemini-3.5-flash",
    "gemini_api_thinking": "high",
    "gemini_api_max_output_tokens": "",
    "gemini_web_model": "pro",
    "gemini_thinking": "extended",
    "link_chatgpt": "https://chatgpt.com/",
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
    "share_r2_account_id": "",
    "share_r2_access_key_id": "",
    "share_r2_secret_access_key": "",
    "share_r2_bucket": "private-shares",
    "share_worker_url": "",
    "gpt_api_key": "",
    "gpt_api_endpoint": "https://api.openai.com/v1/responses",
    "gpt_api_translate_model": "gpt-5.6-luna",
    "gpt_api_polish_model": "gpt-5.6-terra",
    "gpt_api_pronoun_model": "gpt-5.6-terra",
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
    "r19_model": "Model Gemini API dịch từ R19",
    "polish_model": "Model hậu dịch",
    "review_bg_model": "Model review chạy nền",
    "review_bg_criteria": "Tiêu chí review nền",
    "pronoun_model": "Model cập nhật xưng hô",
    "review_model": "Model review toàn bộ",
    "context_model": "Model tạo context",
    "gemini_api_thinking": "Cấp độ suy nghĩ",
    "gemini_api_max_output_tokens": "Token đầu ra tối đa",
    "gemini_web_model": "Model Gemini Web (free/pro/thinking)",
    "gemini_thinking": "Mức thinking Gemini Web",
    "link_chatgpt": "Đường dẫn cuộc chat ChatGPT",
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
    "share_r2_account_id": "Share R2 Account ID",
    "share_r2_access_key_id": "Share R2 Access Key ID",
    "share_r2_secret_access_key": "Share R2 Secret Access Key",
    "share_r2_bucket": "Tên bucket share private",
    "share_worker_url": "Đường dẫn Share Worker",
    "gpt_api_key": "GPT API key",
    "gpt_api_endpoint": "Endpoint GPT Responses API",
    "gpt_api_translate_model": "Model GPT API dùng để dịch",
    "gpt_api_polish_model": "Model GPT API dùng để hiệu đính",
    "gpt_api_pronoun_model": "Model GPT API cập nhật xưng hô",
    "gpt_api_translate_effort": "Reasoning effort khi dịch",
    "gpt_api_polish_effort": "Reasoning effort khi hiệu đính",
    "gpt_api_max_output_tokens": "Số token đầu ra tối đa GPT API",
    "gpt_api_timeout": "Thời gian chờ GPT API (giây)",
    "gpt_api_retries": "Số lần thử lại GPT API",
    "gpt_api_temperature": "Temperature GPT API (để trống = mặc định)",
    "lan_enabled": "Truy cập từ điện thoại cùng Wi-Fi",
    "lan_pin": "Mã PIN truy cập LAN",
}
SECRET_SETTINGS = {"hako_password", "r2_access_key_id", "r2_secret_access_key", "share_r2_access_key_id", "share_r2_secret_access_key", "gpt_api_key", "lan_pin"}
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
    "r19_model": {"group": "gemini-api", "description": "Model API riêng dùng để dịch từng từ/cụm R19 chưa có trong cache."},
    "polish_model": {"group": "gemini-api", "description": "Model biên tập sau khi dịch. Để trống hoặc nhập none để bỏ qua."},
    "review_bg_model": {"group": "gemini-api", "description": "Model review nhanh chạy nền. Để trống hoặc nhập none để bỏ qua."},
    "review_bg_criteria": {"group": "general", "type": "textarea", "description": "Các tiêu chí được chèn trực tiếp vào prompt review từng chương."},
    "pronoun_model": {"group": "gemini-api", "description": "Model trích xuất và cập nhật pronouns.yaml. Để trống hoặc nhập none để bỏ qua."},
    "review_model": {"group": "gemini-api", "description": "Model dùng khi review toàn bộ truyện. Để trống hoặc nhập none để bỏ qua."},
    "context_model": {"group": "gemini-api", "description": "Model Gemini API dùng để tạo glossary trong context.yaml. Để trống hoặc nhập none để bỏ qua."},
    "gemini_api_thinking": {"group": "gemini-api", "type": "select", "options": [
        ["auto", "Tự động theo model"], ["off", "Tắt"], ["minimal", "Minimal"],
        ["low", "Low"], ["medium", "Medium"], ["high", "High"],
    ], "description": "Model không hỗ trợ một mức cụ thể có thể trả lỗi; khi đó chọn Tự động."},
    "gemini_api_max_output_tokens": {"group": "gemini-api", "inputmode": "numeric", "description": "Để trống để dùng giới hạn của model."},
    "gemini_web_model": {"group": "gemini-web"},
    "gemini_thinking": {"group": "gemini-web"},
    "link_chatgpt": {"group": "chatgpt-web"},
    "chatgpt_model": {"group": "chatgpt-web"},
    "chatgpt_thinking": {"group": "chatgpt-web"},
    "fix_max_retry": {"group": "general"},
    "previous_context_chapters": {"group": "general", "description": "Số bản dịch liền trước được đưa vào prompt. Mặc định: 3."},
    "hako_username": {"group": "publishing"}, "hako_password": {"group": "publishing"},
    "hako_management_url": {"group": "publishing"}, "r2_account_id": {"group": "publishing"},
    "r2_access_key_id": {"group": "publishing"}, "r2_secret_access_key": {"group": "publishing"},
    "r2_bucket": {"group": "publishing"}, "r2_public_url": {"group": "publishing"},
    "share_r2_account_id": {"group": "sharing"},
    "share_r2_access_key_id": {"group": "sharing"},
    "share_r2_secret_access_key": {"group": "sharing"},
    "share_r2_bucket": {"group": "sharing", "description": "Bucket private riêng; không bật r2.dev hoặc public domain."},
    "share_worker_url": {"group": "sharing", "description": "URL Worker đã bind bucket share, ví dụ https://aiko-share.example.workers.dev"},
    "gpt_api_key": {"group": "gpt-api"}, "gpt_api_endpoint": {"group": "gpt-api"},
    "gpt_api_translate_model": {"group": "gpt-api"},
    "gpt_api_polish_model": {"group": "gpt-api", "description": "Để trống hoặc nhập none để bỏ qua bước hiệu đính."},
    "gpt_api_pronoun_model": {"group": "gpt-api", "description": "Model trích xuất và cập nhật pronouns.yaml. Để trống hoặc nhập none để bỏ qua."},
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
    "link_gemini", "translate_model", "r19_model", "gemini_web_model", "gemini_thinking",
    "link_chatgpt", "chatgpt_model", "chatgpt_thinking", "fix_max_retry",
    "gpt_api_endpoint", "gpt_api_translate_model",
    "gpt_api_translate_effort", "gpt_api_polish_effort",
}
HIDDEN_SETTINGS = {"r19_model"}


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
            if key not in HIDDEN_SETTINGS
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
            max_length = 5000 if key == "review_bg_criteria" else 500
            if (not value and key not in OPTIONAL_SETTINGS) or len(value) > max_length:
                raise ValueError(f"{SETTING_LABELS[key]} không hợp lệ")
            if value and key == "gemini_api_thinking" and value not in {"auto", "off", "minimal", "low", "medium", "high"}:
                raise ValueError("Cấp độ suy nghĩ Gemini API không hợp lệ")
            if key == "lan_enabled" and value not in {"off", "on"}:
                raise ValueError("Chế độ truy cập LAN không hợp lệ")
            if key == "lan_pin" and value and not re.fullmatch(r"\d{6,12}", value):
                raise ValueError("Mã PIN LAN phải gồm 6–12 chữ số")
            if value and key == "gemini_api_max_output_tokens":
                try:
                    number = float(value)
                except ValueError:
                    raise ValueError(f"{SETTING_LABELS[key]} phải là một số") from None
                if number < 1:
                    raise ValueError(f"{SETTING_LABELS[key]} nằm ngoài phạm vi cho phép")
                if not number.is_integer():
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


def _cloudflare_api(account_id: str, api_token: str, method: str, path: str, body=None, headers=None):
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
    except HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            message = "; ".join(str(item.get("message", "")) for item in error_payload.get("errors", []))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(exc.reason)
        raise ValueError(f"Cloudflare trả lỗi {exc.code}: {message or exc.reason}") from None
    except URLError as exc:
        raise ValueError(f"Không kết nối được Cloudflare: {exc.reason}") from None
    if not payload.get("success", False):
        message = "; ".join(str(item.get("message", "")) for item in payload.get("errors", []))
        raise ValueError(message or "Cloudflare từ chối yêu cầu")
    return payload.get("result")


def _multipart_worker(source: bytes, bucket: str):
    boundary = f"----Aiko{secrets.token_hex(16)}"
    metadata = json.dumps({
        "main_module": "index.js",
        "compatibility_date": datetime.now(timezone.utc).date().isoformat(),
        "bindings": [{"type": "r2_bucket", "name": "SHARE_BUCKET", "bucket_name": bucket}],
    }).encode("utf-8")
    chunks = []
    for name, filename, content_type, value in (
        ("metadata", None, "application/json", metadata),
        ("index.js", "index.js", "application/javascript+module", source),
    ):
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode()
            + value + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def deploy_share_worker(payload: dict):
    account_id = str(payload.get("account_id", "")).strip()
    api_token = str(payload.get("api_token", "")).strip()
    bucket = str(payload.get("bucket", "private-shares")).strip()
    worker_name = str(payload.get("worker_name", "aiko-share-reader")).strip().lower()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
        raise ValueError("Cloudflare Account ID phải gồm 32 ký tự hex")
    if not api_token or len(api_token) > 500:
        raise ValueError("API Token không hợp lệ")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", bucket):
        raise ValueError("Tên bucket phải gồm 3–64 ký tự thường, số hoặc dấu gạch ngang")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", worker_name):
        raise ValueError("Tên Worker phải gồm 1–63 ký tự thường, số hoặc dấu gạch ngang")

    token_identity = _cloudflare_api(account_id, api_token, "GET", "/user/tokens/verify") or {}
    access_key_id = str(token_identity.get("id", "")).strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", access_key_id):
        raise ValueError("Cloudflare không trả về ID hợp lệ cho API Token")
    secret_access_key = hashlib.sha256(api_token.encode("utf-8")).hexdigest()

    result = _cloudflare_api(account_id, api_token, "GET", "/r2/buckets") or {}
    bucket_names = {item.get("name") for item in result.get("buckets", [])}
    bucket_created = bucket not in bucket_names
    if bucket_created:
        _cloudflare_api(account_id, api_token, "POST", "/r2/buckets", {"name": bucket})

    source = (ROOT / "cloudflare" / "share-worker" / "src" / "index.js").read_bytes()
    worker_body, content_type = _multipart_worker(source, bucket)
    script_path = f"/workers/scripts/{quote(worker_name, safe='')}"
    _cloudflare_api(account_id, api_token, "PUT", script_path, worker_body, {"Content-Type": content_type})
    try:
        subdomain_result = _cloudflare_api(account_id, api_token, "GET", "/workers/subdomain") or {}
    except ValueError:
        subdomain_result = {}
    account_subdomain = str(subdomain_result.get("subdomain", "")).strip()
    if not account_subdomain:
        generated_subdomain = "aiko-" + hashlib.sha256(account_id.encode("ascii")).hexdigest()[:10]
        result = _cloudflare_api(account_id, api_token, "PUT", "/workers/subdomain", {"subdomain": generated_subdomain}) or {}
        account_subdomain = str(result.get("subdomain", generated_subdomain)).strip()
    _cloudflare_api(account_id, api_token, "POST", f"{script_path}/subdomain", {"enabled": True, "previews_enabled": False})
    worker_url = f"https://{worker_name}.{account_subdomain}.workers.dev"

    saved = saved_settings()
    saved.update({
        "share_r2_account_id": account_id,
        "share_r2_access_key_id": access_key_id,
        "share_r2_secret_access_key": secret_access_key,
        "share_r2_bucket": bucket,
        "share_worker_url": worker_url,
    })
    write_settings({"values": {key: saved.get(key, default) for key, default in SETTING_DEFAULTS.items()}})
    return {"ok": True, "bucket_created": bucket_created, "worker_url": worker_url, **settings_payload()}


def setup_publishing_r2(payload: dict):
    account_id = str(payload.get("account_id", "")).strip()
    api_token = str(payload.get("api_token", "")).strip()
    bucket = str(payload.get("bucket", "")).strip() or "aiko-images"
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
        raise ValueError("Cloudflare Account ID phải gồm 32 ký tự hex")
    if not api_token or len(api_token) > 500:
        raise ValueError("API Token không hợp lệ")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", bucket):
        raise ValueError("Tên bucket phải gồm 3–64 ký tự thường, số hoặc dấu gạch ngang")

    token_identity = _cloudflare_api(account_id, api_token, "GET", "/user/tokens/verify") or {}
    access_key_id = str(token_identity.get("id", "")).strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", access_key_id):
        raise ValueError("Cloudflare không trả về ID hợp lệ cho API Token")
    secret_access_key = hashlib.sha256(api_token.encode("utf-8")).hexdigest()

    result = _cloudflare_api(account_id, api_token, "GET", "/r2/buckets") or {}
    bucket_names = {item.get("name") for item in result.get("buckets", [])}
    bucket_created = bucket not in bucket_names
    if bucket_created:
        _cloudflare_api(account_id, api_token, "POST", "/r2/buckets", {"name": bucket})
    managed = _cloudflare_api(
        account_id, api_token, "PUT",
        f"/r2/buckets/{quote(bucket, safe='')}/domains/managed",
        {"enabled": True},
    ) or {}
    public_domain = str(managed.get("domain", "")).strip()
    if not public_domain:
        raise ValueError("Cloudflare chưa trả về đường dẫn public của bucket")

    saved = saved_settings()
    saved.update({
        "r2_account_id": account_id,
        "r2_access_key_id": access_key_id,
        "r2_secret_access_key": secret_access_key,
        "r2_bucket": bucket,
        "r2_public_url": f"https://{public_domain}",
    })
    write_settings({"values": {key: saved.get(key, default) for key, default in SETTING_DEFAULTS.items()}})
    return {
        "ok": True,
        "bucket_created": bucket_created,
        "public_url": f"https://{public_domain}",
        **settings_payload(),
    }


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
    active_index = 0
    try:
        fingerprint = json.loads(
            GEMINI_API_KEY_STATE_FILE.read_text(encoding="utf-8")
        ).get("current_key_fingerprint", "")
        active_index = next(
            (
                index
                for index, key in enumerate(keys)
                if hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] == fingerprint
            ),
            0,
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {"keys": keys, "count": len(keys), "active_index": active_index}


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
    return {**gemini_api_keys_payload(), "count": len(cleaned)}


def set_active_gemini_api_key(payload: dict):
    keys = gemini_api_keys_payload()["keys"]
    try:
        index = int(payload.get("active_index"))
    except (TypeError, ValueError):
        raise ValueError("Vị trí API key không hợp lệ") from None
    if index < 0 or index >= len(keys):
        raise ValueError("API key đã chọn không tồn tại")
    temporary = GEMINI_API_KEY_STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "current_key_fingerprint": hashlib.sha256(
                    keys[index].encode("utf-8")
                ).hexdigest()[:16]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, GEMINI_API_KEY_STATE_FILE)
    return {"ok": True, "active_index": index, "count": len(keys)}


def test_gemini_api_key(payload: dict):
    key = str(payload.get("key", "")).strip()
    if not key or len(key) > 500 or any(char.isspace() for char in key):
        raise ValueError("Gemini API key không hợp lệ")

    from google import genai
    from google.genai import types

    model = str(saved_settings().get("translate_model", SETTING_DEFAULTS["translate_model"])).strip()
    try:
        client = genai.Client(api_key=key)
        client.models.generate_content(
            model=model,
            contents="Reply with OK only.",
            config=types.GenerateContentConfig(max_output_tokens=8),
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in (400, 401, 403):
            message = "Key sai, bị chặn hoặc không có quyền"
        elif code == 429:
            message = "Hết quota hoặc bị giới hạn tần suất"
        elif code == 404:
            message = f"Model {model} không khả dụng"
        else:
            code = "NETWORK"
            message = "Không thể kết nối Gemini"
        return {"ok": False, "code": str(code), "message": message, "model": model}
    return {"ok": True, "code": "OK", "message": "Sinh nội dung thành công", "model": model}


def _r19_project_enabled(project_name: str) -> bool:
    if not project_name:
        return False
    path = safe_project(project_name) / ".r19.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("enabled", False)) if isinstance(data, dict) else False


def r19_payload(project_name: str = ""):
    try:
        words = R19_WORDS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        try:
            words = R19_DEFAULT_WORDS_FILE.read_text(encoding="utf-8")
        except FileNotFoundError:
            words = ""
    try:
        config = json.loads(R19_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    terms = [source for line in words.splitlines() if line.strip() and not line.lstrip().startswith("#") for source in [line.partition("=")[0].strip()] if source]
    defaults = {
        "model": R19_DEFAULT_MODEL,
        "context_chapters": R19_DEFAULT_CONTEXT_CHAPTERS,
        "prompt_prefix": R19_DEFAULT_PROMPT_PREFIX,
        "words": R19_DEFAULT_WORDS_FILE.read_text(encoding="utf-8")
        if R19_DEFAULT_WORDS_FILE.exists()
        else "",
    }
    return {
        "enabled": _r19_project_enabled(project_name),
        "words": words,
        "count": len(dict.fromkeys(term.casefold() for term in terms if term)),
        "model": str(config.get("model", defaults["model"])),
        "context_chapters": int(config.get("context_chapters", defaults["context_chapters"])),
        "prompt_prefix": str(config.get("prompt_prefix", R19_DEFAULT_PROMPT_PREFIX)),
        "defaults": defaults,
    }


def write_r19(project_name: str, payload: dict):
    words = str(payload.get("words", "")).replace("\r\n", "\n").replace("\r", "\n")
    if len(words) > 100_000:
        raise ValueError("Danh sách R19 vượt quá 100.000 ký tự")
    terms = [source for line in words.splitlines() if line.strip() and not line.lstrip().startswith("#") for source in [line.partition("=")[0].strip()] if source]
    if len(terms) > 5000 or any(len(term) > 200 for term in terms):
        raise ValueError("Danh sách R19 chỉ hỗ trợ tối đa 5.000 dòng, mỗi dòng 200 ký tự")
    enabled = bool(payload.get("enabled", False))
    if enabled and not terms:
        raise ValueError("Hãy thêm ít nhất một cụm từ trước khi bật Dịch R19")
    model = str(payload.get("model", R19_DEFAULT_MODEL)).strip()
    prompt_prefix = str(payload.get("prompt_prefix", R19_DEFAULT_PROMPT_PREFIX)).strip()
    try:
        context_chapters = int(payload.get("context_chapters", R19_DEFAULT_CONTEXT_CHAPTERS))
    except (TypeError, ValueError):
        raise ValueError("Số chương ngữ cảnh R19 phải là số nguyên") from None
    if not model or len(model) > 200:
        raise ValueError("Model dịch từ R19 không hợp lệ")
    if not prompt_prefix or len(prompt_prefix) > 2000:
        raise ValueError("Dòng mở đầu prompt R19 không hợp lệ")
    if not 0 <= context_chapters <= 20:
        raise ValueError("Số chương ngữ cảnh R19 phải từ 0 đến 20")
    words_temporary = R19_WORDS_FILE.with_suffix(".tmp")
    words_temporary.write_text(words.rstrip() + "\n" if words.strip() else "", encoding="utf-8")
    os.replace(words_temporary, R19_WORDS_FILE)
    R19_CONFIG_FILE.parent.mkdir(exist_ok=True)
    temporary = R19_CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "model": model,
                "context_chapters": context_chapters,
                "prompt_prefix": prompt_prefix,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, R19_CONFIG_FILE)
    project_config = safe_project(project_name) / ".r19.json"
    project_temporary = project_config.with_suffix(".tmp")
    project_temporary.write_text(
        json.dumps({"enabled": enabled}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(project_temporary, project_config)
    return r19_payload(project_name)


def r19_enabled(project_name: str):
    return r19_payload(project_name)["enabled"]


def r19_task_options(project_name: str):
    data = r19_payload(project_name)
    options = {
        "r19_mode": data["enabled"],
        "r19_model": data["model"],
        "r19_prompt_prefix": data["prompt_prefix"],
    }
    if data["enabled"]:
        options["previous_context_chapters"] = data["context_chapters"]
    return options


def _log_r19_page_call(project_name, source, model, prompt, response, ok):
    log_dir = safe_project(project_name) / "logs"
    log_dir.mkdir(exist_ok=True)
    now = datetime.now()
    entry = {
        "ts": now.isoformat(timespec="seconds"),
        "chapter_id": f"r19:{source}",
        "step": "r19_word",
        "model": model,
        "ok": ok,
        "prompt_len": len(prompt),
        "response_len": len(response),
        "prompt": prompt,
        "response": response,
    }
    with (log_dir / f"{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


_LOG_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)


def _redact_log_text(value):
    text = str(value or "")
    text = _LOG_SECRET_PATTERNS[0].sub(r"\1[REDACTED]", text)
    for pattern in _LOG_SECRET_PATTERNS[1:]:
        text = pattern.sub("[REDACTED]", text)
    return text


def ai_logs_data(project_name: str, limit=200):
    log_dir = safe_project(project_name) / "logs"
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 200
    entries = []
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("*.jsonl"), reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                entry["prompt"] = _redact_log_text(entry.get("prompt"))
                entry["response"] = _redact_log_text(entry.get("response"))
                attachments = []
                for attachment in entry.get("attachments", []):
                    if not isinstance(attachment, dict):
                        continue
                    attachments.append(
                        {
                            "name": str(attachment.get("name", "Tệp đính kèm")),
                            "content": _redact_log_text(attachment.get("content")),
                        }
                    )
                entry["attachments"] = attachments
                entries.append(entry)
                if len(entries) >= limit:
                    return {"items": entries, "count": len(entries), "limit": limit}
    return {"items": entries, "count": len(entries), "limit": limit}


def clear_ai_logs(project_name: str):
    log_dir = safe_project(project_name) / "logs"
    removed = 0
    if log_dir.is_dir():
        for path in log_dir.glob("*.jsonl"):
            if path.is_file():
                path.unlink()
                removed += 1
    return {"ok": True, "removed": removed}


def _call_r19_gemini(prompt, model):
    from cores.dich_utils import call_gemini

    return call_gemini(prompt, model=model)


def translate_r19_word(project_name: str, payload: dict):
    source = str(payload.get("source", "")).strip()
    if not source or len(source) > 200 or "\n" in source or "\r" in source:
        raise ValueError("Từ/cụm R19 không hợp lệ")
    safe_project(project_name)
    from cores import r19_translation

    terms, translations = r19_translation.load_word_mappings()
    if source.casefold() not in {term.casefold() for term in terms}:
        raise ValueError("Hãy lưu dòng R19 trước khi dịch")
    cached = translations.get(source.casefold())
    if cached:
        return {**r19_payload(project_name), "source": source, "translation": cached, "cached": True}
    model = r19_payload(project_name)["model"]
    with translation_guard:
        if active_translation():
            raise ValueError("Hãy chờ tác vụ dịch hiện tại kết thúc")
        translation = r19_translation.request_word_translation(
            source,
            "manager",
            model,
            generate=lambda request_prompt: _call_r19_gemini(request_prompt, model),
            logger=lambda request_prompt, request_response, ok: _log_r19_page_call(
                project_name, source, model, request_prompt, request_response, ok
            ),
        )
        r19_translation.save_word_translation(source, translation)
    return {**r19_payload(project_name), "source": source, "translation": translation, "cached": False}


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


def lookup_source_language(text: str):
    if re.search(r"[\uac00-\ud7a3]", text):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u3400-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return "auto"


def google_translate_details(text: str):
    text = text.strip()
    if not text:
        raise ValueError("Chưa chọn nội dung cần dịch")
    if len(text) > 5000:
        raise ValueError("Đoạn được chọn quá dài; tối đa 5.000 ký tự")
    body = urlencode(
        [
            ("client", "gtx"),
            ("sl", lookup_source_language(text)),
            ("tl", "vi"),
            ("dt", "t"),
            ("q", text),
        ]
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
    detected = str(data[2] or "") if len(data) > 2 else ""
    return {
        "translated": translated,
        "detected_language": detected,
    }


def google_translate(text: str):
    return google_translate_details(text)["translated"]


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
    project_text = "\n".join(
        read_live_utf8(raw / name)
        for name in names
        if (raw / name).exists()
    )
    project_character_based = cjk_character_ratio(project_text) > 0.5
    items = []
    for name in names:
        title_path = translated / name if (translated / name).exists() else raw / name
        metric_path = raw / name if (raw / name).exists() else translated / name
        metric = text_metric(metric_path, character_based=project_character_based)
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


def _export_body(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    for index, line in enumerate(lines):
        if line.strip():
            if re.match(r"^\s*#{1,6}\s+", line):
                lines.pop(index)
            break
    return "\n".join(lines).strip()


def _plain_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", lambda m: f"[Hình ảnh: {m.group(1) or 'minh họa'}]", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    return re.sub(r"(?<!\\)[*_~`]", "", text)


def _selected_export_chapters(project_name: str, options: dict):
    items = chapters(project_name)
    scope = str(options.get("scope", "all"))
    if scope == "volume":
        volume = int(options.get("volume", 0))
        items = [item for item in items if re.match(rf"^v{volume}_", item["name"], re.I)]
    elif scope == "range":
        names = [item["name"] for item in items]
        start, end = str(options.get("from", "")), str(options.get("to", ""))
        if start not in names or end not in names:
            raise ValueError("Phạm vi chương không hợp lệ")
        first, last = names.index(start), names.index(end)
        if first > last:
            first, last = last, first
        items = items[first:last + 1]
    elif scope != "all":
        raise ValueError("Phạm vi xuất không hợp lệ")
    if not items:
        raise ValueError("Không có chương nào trong phạm vi đã chọn")

    raw_dir, translated_dir = project_folders(project_name)
    source = str(options.get("source", "translated"))
    if source not in {"translated", "raw", "bilingual"}:
        raise ValueError("Nguồn nội dung không hợp lệ")
    selected = []
    for item in items:
        raw_path = safe_file(raw_dir, item["name"])
        translated_path = safe_file(translated_dir, item["name"])
        raw_text = read_live_utf8(raw_path) if raw_path.exists() else ""
        translated_text = read_live_utf8(translated_path) if translated_path.exists() else ""
        if source == "translated" and not translated_text:
            continue
        if source == "raw" and not raw_text:
            continue
        selected.append({**item, "raw_text": raw_text, "translated_text": translated_text})
    if not selected:
        label = "bản dịch" if source == "translated" else "bản gốc"
        raise ValueError(f"Không tìm thấy {label} trong phạm vi đã chọn")
    return selected, source


def _export_sections(project_name: str, options: dict):
    items, source = _selected_export_chapters(project_name, options)
    sections = []
    for item in items:
        title = item["title"] or item["id"]
        if source == "bilingual":
            body = "### Bản gốc\n\n" + _export_body(item["raw_text"])
            body += "\n\n### Bản dịch\n\n" + _export_body(item["translated_text"])
        else:
            body = _export_body(item[f"{source}_text"])
        sections.append({"title": title, "body": body, "name": item["name"], "project": project_name})
    return sections


def _export_blocks(section: dict):
    project = safe_project(section["project"])
    image_re = re.compile(r"!\[([^\]]*)\]\((?:\.\./)?image/([\w.-]+)\)")
    blocks = []
    cursor = 0
    for match in image_re.finditer(section["body"]):
        text = section["body"][cursor:match.start()]
        for paragraph in re.split(r"\n\s*\n", _plain_markdown(text)):
            value = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
            if value:
                blocks.append(("text", value))
        image_path = (project / "image" / match.group(2)).resolve()
        if image_path.parent == (project / "image").resolve() and image_path.exists():
            blocks.append(("image", image_path, match.group(1)))
        cursor = match.end()
    for paragraph in re.split(r"\n\s*\n", _plain_markdown(section["body"][cursor:])):
        value = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if value:
            blocks.append(("text", value))
    return blocks


def _export_image_asset(path: Path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        width, height = image.size
        extension = path.suffix.lower()
        if extension in {".jpg", ".jpeg", ".png"}:
            return path.read_bytes(), extension, mimetypes.guess_type(path.name)[0], width, height
        output = io.BytesIO()
        if "A" in image.getbands():
            image.save(output, format="PNG")
            return output.getvalue(), ".png", "image/png", width, height
        image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue(), ".jpg", "image/jpeg", width, height


def _docx_paragraph(text: str, style: str | None = None, page_break=False):
    properties = []
    if style:
        properties.append(f'<w:pStyle w:val="{style}"/>')
    if page_break:
        properties.append('<w:pageBreakBefore/>')
    ppr = f"<w:pPr>{''.join(properties)}</w:pPr>" if properties else ""
    value = html_lib.escape(text)
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p>'


def _docx_image_paragraph(relationship_id: str, image_name: str, width: int, height: int, drawing_id: int):
    name = html_lib.escape(image_name)
    max_width, max_height = 5257800, 6858000
    scale = min(max_width / max(width, 1), max_height / max(height, 1))
    cx, cy = max(1, round(width * scale)), max(1, round(height * scale))
    return f'''<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="160"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{drawing_id}" name="{name}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="{drawing_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{relationship_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''


def _build_docx(project_name: str, sections: list[dict]) -> bytes:
    paragraphs = [_docx_paragraph(project_name, "Title")]
    images = []
    for section in sections:
        paragraphs.append(_docx_paragraph(section["title"], "Heading1", page_break=True))
        for block in _export_blocks(section):
            if block[0] == "text":
                paragraphs.append(_docx_paragraph(block[1]))
            else:
                relationship_id = f"rId{len(images) + 2}"
                data, extension, mime_type, width, height = _export_image_asset(block[1])
                target = f"media/image{len(images) + 1}{extension}"
                images.append((relationship_id, target, data, mime_type))
                paragraphs.append(_docx_image_paragraph(relationship_id, block[1].name, width, height, len(images)))
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>' \
        + "".join(paragraphs) + \
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1134" w:right="1276" w:bottom="1134" w:left="1276"/></w:sectPr></w:body></w:document>'
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos" w:eastAsia="Yu Mincho"/><w:sz w:val="22"/><w:lang w:val="vi-VN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="330" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="360"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="44"/><w:szCs w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="300"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="177E68"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
</w:styles>'''
    image_types = {Path(target).suffix.lower().lstrip(".") for _, target, _, _ in images}
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
    type_defaults = "".join(f'<Default Extension="{ext}" ContentType="{mime_map.get(ext, f"image/{ext}")}"/>' for ext in sorted(image_types))
    content_types = f'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>{type_defaults}<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    image_rels = "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"/>' for rid, target, _data, _mime in images)
    doc_rels = f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>{image_rels}</Relationships>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", doc_rels)
        for _rid, target, data, _mime in images:
            archive.writestr(f"word/{target}", data)
    return output.getvalue()


def _build_epub(project_name: str, sections: list[dict]) -> bytes:
    book_id = str(uuid.uuid4())
    chapter_files, nav_items, manifest, spine, images = [], [], [], [], {}
    css = "body{font-family:serif;line-height:1.65;margin:5%;}h1{font-size:1.45em;}h2{font-size:1.1em;}p{text-align:justify;margin:.65em 0;}figure{margin:1em 0;text-align:center;}img{max-width:100%;height:auto;}"
    for index, section in enumerate(sections, 1):
        filename = f"chapter-{index}.xhtml"
        blocks = []
        for block in _export_blocks(section):
            if block[0] == "text":
                blocks.append(f"<p>{html_lib.escape(block[1])}</p>")
            else:
                key = str(block[1])
                if key not in images:
                    data, extension, mime_type, _width, _height = _export_image_asset(block[1])
                    images[key] = (f"images/image-{len(images)+1}{extension}", data, mime_type)
                image_href, _data, _mime = images[key]
                blocks.append(f'<figure><img src="{html_lib.escape(image_href)}" alt="{html_lib.escape(block[2])}"/></figure>')
        page = f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="vi"><head><title>{html_lib.escape(section['title'])}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body><h1>{html_lib.escape(section['title'])}</h1>{''.join(blocks)}</body></html>'''
        chapter_files.append((filename, page))
        nav_items.append(f'<li><a href="{filename}">{html_lib.escape(section["title"])}</a></li>')
        manifest.append(f'<item id="c{index}" href="{filename}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{index}"/>')
    nav = f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Mục lục</title></head><body><nav epub:type="toc"><h1>Mục lục</h1><ol>{''.join(nav_items)}</ol></nav></body></html>'''
    image_manifest = "".join(f'<item id="img{i}" href="{href}" media-type="{mime_type}"/>' for i, (href, _data, mime_type) in enumerate(images.values(), 1))
    opf = f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">urn:uuid:{book_id}</dc:identifier><dc:title>{html_lib.escape(project_name)}</dc:title><dc:language>vi</dc:language><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="css" href="style.css" media-type="text/css"/>{''.join(manifest)}{image_manifest}</manifest><spine>{''.join(spine)}</spine></package>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for filename, page in chapter_files:
            archive.writestr(f"OEBPS/{filename}", page, compress_type=zipfile.ZIP_DEFLATED)
        for href, data, _mime in images.values():
            archive.writestr(f"OEBPS/{href}", data, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def export_book(project_name: str, options: dict):
    export_format = str(options.get("format", "epub")).lower()
    if export_format not in {"epub", "docx", "markdown"}:
        raise ValueError("Định dạng xuất không được hỗ trợ")
    sections = _export_sections(project_name, options)
    safe_name = re.sub(r"[^\w.-]+", "-", project_name, flags=re.UNICODE).strip("-.") or "truyen"
    if export_format == "markdown":
        content = f"# {project_name}\n\n" + "\n\n".join(f"## {item['title']}\n\n{item['body']}" for item in sections)
        return content.encode("utf-8"), "text/markdown; charset=utf-8", f"{safe_name}.md"
    if export_format == "docx":
        return _build_docx(project_name, sections), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{safe_name}.docx"
    return _build_epub(project_name, sections), "application/epub+zip", f"{safe_name}.epub"


SHARE_SEGMENT_RE = re.compile(r"^v(\d+)_c(\d+)_s(\d+)\.md$", re.IGNORECASE)


def _share_chapter_identity(name: str):
    match = re.match(r"^v(\d+)_c(\d+)(?:_s\d+)?\.md$", name, re.IGNORECASE)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _share_chapter_groups(paths):
    groups = {}
    for path in paths:
        match = SHARE_SEGMENT_RE.match(path.name)
        if match:
            volume, chapter, segment = map(int, match.groups())
            identity = (volume, chapter)
            group = groups.setdefault(identity, {"identity": identity, "name": f"v{volume}_c{chapter}.md", "paths": []})
            group["paths"].append((segment, path))
        else:
            identity = ("file", path.name.casefold())
            group = groups.setdefault(identity, {"identity": None, "name": path.name, "paths": []})
            group["paths"].append((0, path))
    result = []
    for group in groups.values():
        group["paths"] = [path for _segment, path in sorted(group["paths"], key=lambda item: (item[0], item[1].name.casefold()))]
        result.append(group)
    return sorted(result, key=lambda item: chapter_key(item["name"]))


def _share_merged_markdown(paths):
    title = chapter_title(paths[0])
    bodies = []
    for path in paths:
        lines = read_live_utf8(path).splitlines()
        for index, line in enumerate(lines):
            if line.strip():
                if re.match(r"^\s*#{1,6}\s+", line):
                    del lines[index]
                break
        body = "\n".join(lines).strip()
        if body:
            bodies.append(body)
    content = f"# {title}"
    if bodies:
        content += "\n\n" + "\n\n".join(bodies)
    return content, title


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


def clean_metric_text(text: str) -> str:
    clean = re.sub(r"\[img\][\s\S]*?\[/img\]", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"^[#>\-+*]+\s*", " ", clean, flags=re.MULTILINE)
    return re.sub(r"[*_~`]+", " ", clean)


def cjk_character_ratio(text: str) -> float:
    clean = re.sub(r"\s+", "", clean_metric_text(text))
    if not clean:
        return 0.0
    cjk = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", clean)
    return len(cjk) / len(clean)


def text_metric(path: Path, character_based=None) -> dict:
    try:
        text = read_live_utf8(path)
    except OSError:
        return {"count": 0, "unit": "từ"}
    clean = clean_metric_text(text)
    if character_based is None:
        character_based = cjk_character_ratio(clean) > 0.5
    if character_based:
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
        return {
            "index": 0,
            "glossary": [],
            "style_notes": "",
            "prompt_preset": "default",
            "prompt_role": DEFAULT_ROLE,
            "prompt_task": DEFAULT_TASK,
            "prompt_presets": prompt_presets_payload(),
            "polish_prompt_preset": "default",
            "polish_prompt_role": DEFAULT_POLISH_ROLE,
            "polish_prompt_task": DEFAULT_POLISH_TASK,
            "polish_prompt_presets": polish_prompt_presets_payload(),
            "raw_yaml": "",
        }
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
        "prompt_preset": str(data.get("prompt_preset", "default")),
        "prompt_role": str(data.get("prompt_role", "")).strip() or DEFAULT_ROLE,
        "prompt_task": str(data.get("prompt_task", "")).strip() or DEFAULT_TASK,
        "prompt_presets": prompt_presets_payload(),
        "polish_prompt_preset": str(data.get("polish_prompt_preset", "default")),
        "polish_prompt_role": str(data.get("polish_prompt_role", "")).strip() or DEFAULT_POLISH_ROLE,
        "polish_prompt_task": str(data.get("polish_prompt_task", "")).strip() or DEFAULT_POLISH_TASK,
        "polish_prompt_presets": polish_prompt_presets_payload(),
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


def hako_public_chapters(public_url: str):
    public_url = str(public_url or "").strip()
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or parsed.hostname not in {"docln.sbs", "ln.hako.vn"}:
        raise ValueError("Hãy nhập URL trang truyện Hako hợp lệ")
    if not re.fullmatch(r"/truyen/\d+(?:-[^/?#]+)?/?", parsed.path):
        raise ValueError("URL phải là trang truyện Hako, không phải URL một chương")
    canonical_url = f"https://docln.sbs{parsed.path.rstrip('/')}"
    request = Request(canonical_url, headers={"User-Agent": "Mozilla/5.0 Aiko-App-Translator"})
    try:
        source = urlopen(request, timeout=20).read().decode("utf-8", "replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Không tải được danh sách chương Hako: {exc}") from None
    pattern = re.compile(
        r'<a\b[^>]*href=["\'](?P<href>[^"\']*/c(?P<id>\d+)-[^"\']*)["\'][^>]*>(?P<title>[\s\S]*?)</a>',
        re.IGNORECASE,
    )
    items, seen = [], set()
    for match in pattern.finditer(source):
        chapter_id = match.group("id")
        if chapter_id in seen:
            continue
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group("title")))
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        href = match.group("href")
        if href.startswith("/"):
            href = "https://docln.sbs" + href
        items.append({"chapter_id": chapter_id, "title": title, "url": href})
        seen.add(chapter_id)
    if not items:
        raise ValueError("Không tìm thấy chương nào trên trang Hako này")
    return {"url": canonical_url, "items": items, "total": len(items)}


def validate_hako_edit_targets(value):
    if not isinstance(value, list) or not value or len(value) > 50:
        raise ValueError("Danh sách chương Hako cần cập nhật không hợp lệ")
    normalized, seen = [], set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Mapping Hako dòng {index} không hợp lệ")
        local_name = str(item.get("local_name", "")).strip()
        chapter_id = str(item.get("chapter_id", "")).strip()
        remote_title = str(item.get("remote_title", "")).strip()
        if not re.fullmatch(r"v\d+_c\d+_s\d+\.md", local_name):
            raise ValueError(f"Tên chương local dòng {index} không hợp lệ")
        if not chapter_id.isdigit() or len(chapter_id) > 20:
            raise ValueError(f"Chapter ID Hako dòng {index} không hợp lệ")
        if not remote_title or len(remote_title) > 500:
            raise ValueError(f"Tiêu đề Hako dòng {index} không hợp lệ")
        if chapter_id in seen:
            raise ValueError(f"Chapter ID {chapter_id} bị chọn trùng")
        seen.add(chapter_id)
        normalized.append(
            {
                "local_name": local_name,
                "chapter_id": chapter_id,
                "remote_title": remote_title,
            }
        )
    return normalized


def _share_store_path(project_name: str) -> Path:
    return safe_project(project_name) / "sharing.yaml"


def _share_r2_config() -> dict:
    settings = {**SETTING_DEFAULTS, **saved_settings()}
    config = {
        "account_id": str(settings.get("share_r2_account_id", "")).strip(),
        "access_key_id": str(settings.get("share_r2_access_key_id", "")).strip(),
        "secret_access_key": str(settings.get("share_r2_secret_access_key", "")).strip(),
        "bucket": str(settings.get("share_r2_bucket", "")).strip(),
        "worker_url": str(settings.get("share_worker_url", "")).strip().rstrip("/"),
    }
    missing = [key for key in ("account_id", "access_key_id", "secret_access_key", "bucket") if not config[key]]
    if missing:
        raise ValueError("Chưa cấu hình đầy đủ bucket R2 share private")
    return config


def _share_r2_client(config: dict):
    if boto3 is None:
        raise ValueError("Thiếu boto3; hãy cài requirements-portable.txt")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=config["access_key_id"],
        aws_secret_access_key=config["secret_access_key"],
        region_name="auto",
    )


def _load_shares(project_name: str) -> list[dict]:
    path = _share_store_path(project_name)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    shares = data.get("shares", []) if isinstance(data, dict) else []
    return shares if isinstance(shares, list) else []


def _save_shares(project_name: str, shares: list[dict]):
    path = _share_store_path(project_name)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(yaml.safe_dump({"shares": shares}, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(temporary, path)


def shares_data(project_name: str) -> dict:
    config = {**SETTING_DEFAULTS, **saved_settings()}
    worker_url = str(config.get("share_worker_url", "")).strip().rstrip("/")
    items = []
    for share in _load_shares(project_name):
        item = dict(share)
        token = str(item.pop("token", ""))
        item["url"] = f"{worker_url}/?share={quote(str(item.get('id', '')))}&token={quote(token)}" if worker_url and token else ""
        items.append(item)
    return {"items": items, "configured": bool(worker_url and config.get("share_r2_bucket"))}


def _share_manifest(share: dict) -> dict:
    return {
        "version": 1,
        "id": share["id"],
        "title": share["title"],
        "recipient": share.get("recipient", ""),
        "expires_at": share["expires_at"],
        "token_hash": hashlib.sha256(str(share["token"]).encode("utf-8")).hexdigest(),
        "chapters": share.get("chapters", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _share_chapter_html(project_name: str, text: str, share_id: str):
    images = []
    output = []
    for raw_line in unicodedata.normalize("NFC", text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        local_image = re.fullmatch(r"!\[([^\]]*)\]\((?:\.\./)?image/([\w.-]+)\)", line)
        remote_image = re.fullmatch(r"\[img(?:=[^\]]+)?\](https?://[^\[]+)\[/img\]", line, re.IGNORECASE)
        if local_image:
            name = local_image.group(2)
            path = safe_image(project_name, name)
            if path.is_file():
                item = {
                    "name": name,
                    "key": f"shares/{share_id}/images/{name}",
                    "content_type": {
                        ".webp": "image/webp", ".avif": "image/avif", ".png": "image/png",
                        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                    }.get(path.suffix.lower()) or mimetypes.guess_type(name)[0] or "application/octet-stream",
                }
                images.append((item, path))
                caption = html_lib.escape(local_image.group(1).strip() or Path(name).stem)
                output.append(f'<figure><img data-share-image="{html_lib.escape(name, quote=True)}" alt="{caption}" loading="lazy"><figcaption>{caption}</figcaption></figure>')
            continue
        if remote_image:
            url = html_lib.escape(remote_image.group(1).strip(), quote=True)
            output.append(f'<figure><img src="{url}" alt="" loading="lazy"></figure>')
            continue
        escaped = html_lib.escape(raw_line)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(^|[^*])\*([^*]+?)\*", r"\1<em>\2</em>", escaped)
        if escaped.startswith("### "):
            output.append(f"<h3>{escaped[4:]}</h3>")
        elif escaped.startswith("## "):
            output.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("# "):
            output.append(f"<h1>{escaped[2:]}</h1>")
        else:
            output.append(f"<p>{escaped}</p>")
    return "".join(output), images


def remove_shared_chapter(project_name: str, share_id: str, chapter_name: str) -> dict:
    shares = _load_shares(project_name)
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    if share is None:
        raise ValueError("Không tìm thấy bản share")
    chapter = next((item for item in share.get("chapters", []) if str(item.get("name")) == chapter_name), None)
    if chapter is None:
        raise ValueError("Chương không nằm trong bản share")
    config = _share_r2_config()
    client = _share_r2_client(config)
    share["chapters"] = [item for item in share.get("chapters", []) if str(item.get("name")) != chapter_name]
    client.put_object(
        Bucket=config["bucket"], Key=f"shares/{share_id}/manifest.json",
        Body=json.dumps(_share_manifest(share), ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8", CacheControl="private, no-store",
    )
    remaining_image_keys = {
        str(image.get("key"))
        for item in share["chapters"]
        for image in item.get("images", [])
        if image.get("key")
    }
    keys = [str(chapter["key"])] + [
        str(image.get("key")) for image in chapter.get("images", [])
        if image.get("key") and str(image.get("key")) not in remaining_image_keys
    ]
    client.delete_objects(Bucket=config["bucket"], Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True})
    _save_shares(project_name, shares)
    return shares_data(project_name)


def close_share(project_name: str, share_id: str) -> dict:
    shares = _load_shares(project_name)
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    if share is None:
        raise ValueError("Không tìm thấy bản share")
    config = _share_r2_config()
    keys = [str(item.get("key")) for item in share.get("chapters", []) if item.get("key")]
    keys.extend(
        str(image.get("key"))
        for item in share.get("chapters", [])
        for image in item.get("images", [])
        if image.get("key")
    )
    keys.append(f"shares/{share_id}/manifest.json")
    result = _share_r2_client(config).delete_objects(
        Bucket=config["bucket"], Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )
    if result.get("Errors"):
        raise ValueError("R2 không xóa được toàn bộ dữ liệu của bản share")
    _save_shares(project_name, [item for item in shares if str(item.get("id")) != share_id])
    return shares_data(project_name)


def save_share(project_name: str, payload: dict) -> dict:
    action = str(payload.get("action", "")).strip()
    if action == "remove_chapter":
        return remove_shared_chapter(project_name, str(payload.get("share_id", "")).strip(), str(payload.get("chapter", "")).strip())
    if action == "close":
        return close_share(project_name, str(payload.get("share_id", "")).strip())
    project = safe_project(project_name)
    translated = project / "translated"
    chapter_names = payload.get("chapters", [])
    if not isinstance(chapter_names, list) or not chapter_names:
        raise ValueError("Hãy chọn ít nhất một chương đã dịch")
    chapter_names = [str(name) for name in chapter_names]
    paths = [safe_file(translated, name) for name in chapter_names]
    if any(not path.is_file() for path in paths):
        raise ValueError("Có chương chưa có bản dịch để chia sẻ")

    config = _share_r2_config()
    client = _share_r2_client(config)
    shares = _load_shares(project_name)
    share_id = str(payload.get("share_id", "")).strip()
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    now = datetime.now(timezone.utc)
    if share is None:
        share_id = secrets.token_hex(8)
        share = {
            "id": share_id,
            "token": secrets.token_urlsafe(32),
            "title": str(payload.get("title", project_name)).strip() or project_name,
            "recipient": str(payload.get("recipient", "")).strip(),
            "created_at": now.isoformat(),
            "chapters": [],
        }
        shares.append(share)
    else:
        share["title"] = str(payload.get("title", share.get("title", project_name))).strip() or share.get("title", project_name)
        share["recipient"] = str(payload.get("recipient", share.get("recipient", ""))).strip()
    days = max(1, min(int(payload.get("expires_days", 30)), 3650))
    share["expires_at"] = (now + timedelta(days=days)).isoformat()
    chapter_map = {str(item.get("name")): item for item in share.get("chapters", []) if isinstance(item, dict)}
    stale_keys = []
    for group in _share_chapter_groups(paths):
        content, title = _share_merged_markdown(group["paths"])
        output_name = group["name"]
        key = f"shares/{share_id}/chapters/{output_name}"
        chapter_html, local_images = _share_chapter_html(project_name, content, share_id)
        client.put_object(Bucket=config["bucket"], Key=key, Body=chapter_html.encode("utf-8"), ContentType="text/html; charset=utf-8", CacheControl="private, no-store")
        for image, image_path in local_images:
            client.put_object(Bucket=config["bucket"], Key=image["key"], Body=image_path.read_bytes(), ContentType=image["content_type"], CacheControl="private, no-store")
        aliases = [name for name in chapter_map if name == output_name or (group["identity"] is not None and _share_chapter_identity(name) == group["identity"])]
        for alias in aliases:
            previous = chapter_map.pop(alias)
            if previous.get("key") and str(previous["key"]) != key:
                stale_keys.append(str(previous["key"]))
            stale_keys.extend(str(image.get("key")) for image in previous.get("images", []) if image.get("key"))
        chapter_map[output_name] = {
            "name": output_name, "title": title, "key": key,
            "format": "html", "images": [image for image, _path in local_images],
            "updated_at": now.isoformat(),
        }
    share["chapters"] = sorted(chapter_map.values(), key=lambda item: chapter_key(str(item["name"])))
    active_image_keys = {str(image.get("key")) for item in share["chapters"] for image in item.get("images", []) if image.get("key")}
    stale_keys = [key for key in stale_keys if key not in active_image_keys]
    manifest = _share_manifest(share)
    client.put_object(Bucket=config["bucket"], Key=f"shares/{share_id}/manifest.json", Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"), ContentType="application/json; charset=utf-8", CacheControl="private, no-store")
    if stale_keys:
        client.delete_objects(Bucket=config["bucket"], Delete={"Objects": [{"Key": key} for key in sorted(set(stale_keys))], "Quiet": True})
    _save_shares(project_name, shares)
    return shares_data(project_name)


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
    if "glossary_items" in payload:
        items = payload.get("glossary_items")
        if not isinstance(items, list):
            raise ValueError("Dữ liệu glossary không hợp lệ")
        glossary_lines = []
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Glossary sai định dạng tại dòng {number}")
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            if not source or not target or "=" in source:
                raise ValueError(f"Glossary sai định dạng tại dòng {number}")
            glossary_lines.append(f"{source} = {target}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        data = data or {}
        if not isinstance(data, dict):
            raise ValueError("context.yaml hiện tại không hợp lệ")
        data["glossary"] = "\n".join(glossary_lines)
        write_context_safely(path, data)
        result = context_data(project_name)
        result["backup"] = path.with_name(path.name + ".bak").exists()
        return result
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
        prompt_preset = str(
            fields.get("prompt_preset", data.get("prompt_preset", "default"))
        ).strip()
        if prompt_preset not in {*PROMPT_PRESETS, "custom"}:
            raise ValueError("Preset prompt không hợp lệ")
        prompt_role = str(
            fields.get("prompt_role", data.get("prompt_role", DEFAULT_ROLE))
        ).strip()
        prompt_task = str(
            fields.get("prompt_task", data.get("prompt_task", DEFAULT_TASK))
        ).strip()
        if not prompt_role or len(prompt_role) > 20000:
            raise ValueError("Prompt vai trò phải có từ 1 đến 20.000 ký tự")
        if not prompt_task or len(prompt_task) > 20000:
            raise ValueError("Prompt nhiệm vụ phải có từ 1 đến 20.000 ký tự")
        data["prompt_preset"] = prompt_preset
        data["prompt_role"] = prompt_role
        data["prompt_task"] = prompt_task
        polish_prompt_preset = str(
            fields.get(
                "polish_prompt_preset", data.get("polish_prompt_preset", "default")
            )
        ).strip()
        if polish_prompt_preset not in {*POLISH_PROMPT_PRESETS, "custom"}:
            raise ValueError("Mẫu prompt hiệu đính không hợp lệ")
        polish_prompt_role = str(
            fields.get(
                "polish_prompt_role",
                data.get("polish_prompt_role", DEFAULT_POLISH_ROLE),
            )
        ).strip()
        polish_prompt_task = str(
            fields.get(
                "polish_prompt_task",
                data.get("polish_prompt_task", DEFAULT_POLISH_TASK),
            )
        ).strip()
        if not polish_prompt_role or len(polish_prompt_role) > 20000:
            raise ValueError("Vai trò hiệu đính phải có từ 1 đến 20.000 ký tự")
        if not polish_prompt_task or len(polish_prompt_task) > 20000:
            raise ValueError("Nhiệm vụ hiệu đính phải có từ 1 đến 20.000 ký tự")
        data["polish_prompt_preset"] = polish_prompt_preset
        data["polish_prompt_role"] = polish_prompt_role
        data["polish_prompt_task"] = polish_prompt_task
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


CHAPTER_FILE_RE = re.compile(r"^v(\d+)_c(\d+)_s(\d+)\.md$", re.IGNORECASE)


def _import_chapter_groups(raw_dir: Path):
    groups: dict[tuple[int, int], list[Path]] = {}
    for path in raw_dir.glob("v*_c*_s*.md") if raw_dir.is_dir() else []:
        match = CHAPTER_FILE_RE.match(path.name)
        if match:
            key = (int(match.group(1)), int(match.group(2)))
            groups.setdefault(key, []).append(path)
    for paths in groups.values():
        paths.sort(key=lambda item: int(CHAPTER_FILE_RE.match(item.name).group(3)))
    return groups


def _import_chapter_text(paths):
    parts = [path.read_text(encoding="utf-8", errors="replace") for path in paths]
    return "\n".join(parts)


def _normalized_anchor_text(value, *, title=False):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    if title:
        value = re.sub(r"^(?:chapter|chap|chương|第|제)\s*\d+\s*(?:章|話|话|幕|화|장)?", "", value)
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", "", value)[:1600]


def _chapter_anchor_features(text):
    lines = text.splitlines()
    return (
        _normalized_anchor_text(lines[0] if lines else "", title=True),
        _normalized_anchor_text("\n".join(lines[1:])),
    )


def _chapter_anchor(source_features, existing_features):
    source_title, source_body = source_features
    existing_title, existing_body = existing_features
    title_score = difflib.SequenceMatcher(None, source_title, existing_title).ratio() if source_title and existing_title else 0
    body_score = difflib.SequenceMatcher(None, source_body, existing_body).ratio() if source_body and existing_body else 0
    score = title_score * 0.4 + body_score * 0.6
    valid = body_score >= 0.72 or (title_score >= 0.9 and body_score >= 0.35)
    return score if valid else 0


def create_chapter_import_preview(project_name, source_format, segment_limit, content):
    project = safe_project(project_name)
    raw_dir, _translated = project_folders(project_name)
    if source_format not in {"epub", "txt"}:
        raise ValueError("Chỉ hỗ trợ file EPUB hoặc TXT")
    if not 500 <= segment_limit <= 50000:
        raise ValueError("Giới hạn segment phải từ 500 đến 50.000")
    if not content or len(content) > 300 * 1024 * 1024:
        raise ValueError("File trống hoặc vượt quá 300 MB")
    token = secrets.token_urlsafe(18)
    staging = ROOT / ".runtime" / "chapter-imports" / token
    staging.mkdir(parents=True)
    upload = staging / f"source.{source_format}"
    upload.write_bytes(content)
    try:
        from split.chapter_splitter_novelpia_md import split_epub_to_md, split_txt_to_md

        splitter = split_epub_to_md if source_format == "epub" else split_txt_to_md
        result = splitter(
            str(upload), 0, str(ROOT), project_dir=str(staging),
            segment_limit=segment_limit, return_details=True,
        )
        upload.unlink(missing_ok=True)
        source_groups = _import_chapter_groups(staging / "raw")
        if not source_groups:
            raise ValueError(f"Không tách được chương nào từ {source_format.upper()}")
        existing_groups = _import_chapter_groups(raw_dir)
        existing_texts = {key: _import_chapter_text(paths) for key, paths in existing_groups.items()}
        existing_features = {key: _chapter_anchor_features(text) for key, text in existing_texts.items()}
        title_keys = {}
        body_keys = {}
        for key, (title, body) in existing_features.items():
            if title:
                title_keys.setdefault(title, []).append(key)
            if body:
                body_keys.setdefault(body[:240], []).append(key)
        anchors = []
        chapters = []
        for (_volume, source_index), paths in sorted(source_groups.items()):
            text = _import_chapter_text(paths)
            title = text.splitlines()[0].removeprefix("# ").strip() if text else f"Chương {source_index}"
            source_features = _chapter_anchor_features(text)
            source_title, source_body = source_features
            candidate_keys = set(title_keys.get(source_title, [])) | set(body_keys.get(source_body[:240], []))
            if not candidate_keys and source_title:
                for close_title in difflib.get_close_matches(source_title, title_keys, n=5, cutoff=0.55):
                    candidate_keys.update(title_keys[close_title])
            if not candidate_keys and source_body:
                for close_body in difflib.get_close_matches(source_body[:240], body_keys, n=5, cutoff=0.55):
                    candidate_keys.update(body_keys[close_body])
            ranked = sorted(
                ((_chapter_anchor(source_features, existing_features[key]), key) for key in candidate_keys),
                reverse=True,
            )
            best_score, best_key = ranked[0] if ranked else (0, None)
            second_score = ranked[1][0] if len(ranked) > 1 else 0
            matched = best_key if best_score >= 0.62 and best_score - second_score >= 0.08 else None
            if matched:
                anchors.append((source_index, matched[0], matched[1], best_score))
            chapters.append({
                "source_index": source_index,
                "title": title,
                "segments": len(paths),
                "match": f"v{matched[0]}_c{matched[1]}" if matched else "",
                "match_score": round(best_score, 2) if matched else 0,
            })
        mappings = {}
        for source_index, volume, chapter, _score in anchors:
            mappings.setdefault((volume, chapter - source_index), []).append(source_index)
        best_mapping, mapped_sources = max(mappings.items(), key=lambda item: len(item[1])) if mappings else ((None, None), [])
        if mapped_sources:
            volume, offset = best_mapping
            suggested_from = max(mapped_sources) + 1
            no_new = suggested_from > chapters[-1]["source_index"]
            source_from = chapters[-1]["source_index"] if no_new else suggested_from
            target_start = source_from + offset
            confidence = "high" if len(mapped_sources) >= 2 else "medium"
        else:
            latest = max(existing_groups, default=(1, -1))
            volume, source_from, target_start, confidence = latest[0], chapters[0]["source_index"], latest[1] + 1, "manual"
            no_new = False
        source_to = chapters[-1]["source_index"]
        for chapter in chapters:
            chapter["selected"] = not no_new and source_from <= chapter["source_index"] <= source_to
        chapter_import_previews[token] = {
            "project": project.name,
            "staging": staging,
            "created": time.time(),
            "source_groups": source_groups,
        }
        return {
            **result,
            "token": token,
            "chapters": chapters,
            "chapter_count": result.get("chapters", len(chapters)),
            "source_from": source_from,
            "source_to": source_to,
            "target_volume": volume,
            "target_start": target_start,
            "anchors": len(mapped_sources),
            "confidence": confidence,
            "no_new": no_new,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def confirm_chapter_import(project_name, payload):
    token = str(payload.get("token", ""))
    preview = chapter_import_previews.get(token)
    if not preview or preview["project"] != project_name:
        raise ValueError("Bản xem trước đã hết hạn; hãy phân tích lại file")
    source_from = int(payload.get("source_from", 0))
    source_to = int(payload.get("source_to", -1))
    target_volume = int(payload.get("target_volume", 0))
    target_start = int(payload.get("target_start", 0))
    conflict = str(payload.get("conflict", "skip"))
    if source_from < 0 or source_to < source_from or target_volume < 0 or target_start < 0:
        raise ValueError("Range hoặc chương đích không hợp lệ")
    if conflict not in {"skip", "overwrite"}:
        raise ValueError("Cách xử lý chương trùng không hợp lệ")
    selected = {int(value) for value in payload.get("selected", [])}
    project = safe_project(project_name)
    raw_dir, _translated = project_folders(project_name)
    image_dir = project / "image"
    image_dir.mkdir(exist_ok=True)
    imported = skipped = overwritten = 0
    first_file = ""
    imported_images = set()
    try:
        for (_source_volume, source_index), paths in sorted(preview["source_groups"].items()):
            if not source_from <= source_index <= source_to or (selected and source_index not in selected):
                continue
            target_chapter = target_start + source_index - source_from
            existing = list(raw_dir.glob(f"v{target_volume}_c{target_chapter}_s*.md"))
            if existing and conflict == "skip":
                skipped += 1
                continue
            if existing:
                for path in existing:
                    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
                    path.unlink()
                overwritten += 1
            for segment, source_path in enumerate(paths, 1):
                target = raw_dir / f"v{target_volume}_c{target_chapter}_s{segment}.md"
                shutil.copy2(source_path, target)
                imported_images.update(
                    Path(match).name
                    for match in re.findall(r"\.\./image/([^\s)]+)", source_path.read_text(encoding="utf-8", errors="replace"))
                )
                first_file = first_file or target.name
            imported += 1
        for image_name in imported_images:
            image = preview["staging"] / "image" / image_name
            if image.is_file():
                shutil.copy2(image, image_dir / image.name)
        return {"ok": True, "imported": imported, "skipped": skipped, "overwritten": overwritten, "first_file": first_file}
    finally:
        chapter_import_previews.pop(token, None)
        shutil.rmtree(preview["staging"], ignore_errors=True)


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
    effective_config = {**saved_settings(), **task_config, **r19_task_options(project_name)}
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
        **r19_task_options(project_name),
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

    def download_response(self, body: bytes, content_type: str, filename: str):
        encoded_name = quote(filename)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
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
        if path == "/api/ui-preferences":
            return self.json_response(ui_preferences_data())
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
        if path == "/api/hako/chapters":
            try:
                return self.json_response(
                    hako_public_chapters(query.get("url", [""])[0])
                )
            except ValueError as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/shares":
            try:
                return self.json_response(shares_data(project))
            except (ValueError, OSError, yaml.YAMLError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys":
            return self.json_response(gemini_api_keys_payload())
        if path == "/api/r19":
            return self.json_response(r19_payload(project))
        if path == "/api/ai-logs":
            try:
                return self.json_response(
                    ai_logs_data(project, query.get("limit", ["200"])[0])
                )
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
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
        if path == "/api/ui-preferences":
            try:
                return self.json_response(write_ui_preferences(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/export-book":
            try:
                body, content_type, filename = export_book(project, self.body())
                return self.download_response(body, content_type, filename)
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/ai-logs/clear":
            try:
                return self.json_response(clear_ai_logs(project))
            except (ValueError, OSError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/chapters/import-preview":
            try:
                source_format = query.get("format", ["epub"])[0].lower()
                segment_limit = int(query.get("segment_limit", ["5000"])[0])
                length = int(self.headers.get("Content-Length", 0))
                if not length or length > 300 * 1024 * 1024:
                    raise ValueError("File trống hoặc vượt quá 300 MB")
                content = self.rfile.read(length) if length else b""
                return self.json_response(
                    create_chapter_import_preview(project, source_format, segment_limit, content)
                )
            except Exception as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/chapters/import-confirm":
            try:
                return self.json_response(confirm_chapter_import(project, self.body()))
            except Exception as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/chapters/import-cancel":
            payload = self.body()
            preview = chapter_import_previews.pop(str(payload.get("token", "")), None)
            if preview:
                shutil.rmtree(preview["staging"], ignore_errors=True)
            return self.json_response({"ok": True})
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
        if path == "/api/share-worker/deploy":
            if not self.is_loopback():
                return self.json_response(
                    {"error": "Chỉ được thiết lập Cloudflare trực tiếp trên máy đang chạy app."},
                    HTTPStatus.FORBIDDEN,
                )
            try:
                return self.json_response(deploy_share_worker(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/publishing-r2/setup":
            if not self.is_loopback():
                return self.json_response(
                    {"error": "Chỉ được thiết lập Cloudflare trực tiếp trên máy đang chạy app."},
                    HTTPStatus.FORBIDDEN,
                )
            try:
                return self.json_response(setup_publishing_r2(self.body()))
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
        if path == "/api/shares":
            try:
                return self.json_response(save_share(project, self.body()))
            except Exception as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys":
            try:
                return self.json_response(write_gemini_api_keys(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys/active":
            if active_translation():
                return self.json_response(
                    {"error": "Không thể đổi API key khi đang dịch"},
                    HTTPStatus.CONFLICT,
                )
            try:
                return self.json_response(set_active_gemini_api_key(self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/gemini-api-keys/test":
            try:
                return self.json_response(test_gemini_api_key(self.body()))
            except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/r19":
            try:
                return self.json_response(write_r19(project, self.body()))
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                return self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/r19/translate-word":
            try:
                return self.json_response(translate_r19_word(project, self.body()))
            except (ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
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
                return self.json_response(google_translate_details(text))
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
                    not isinstance(key, str)
                    or (
                        isinstance(value, (dict, list))
                        and not (kind == "hako-edit" and key == "hako_edit_targets")
                    )
                    for key, value in config.items()
                ):
                    raise ValueError("Cấu hình tác vụ không hợp lệ")
                if kind == "hako-edit":
                    config["hako_edit_targets"] = validate_hako_edit_targets(
                        config.get("hako_edit_targets")
                    )
                max_chapters = config.get("max_chapters", "")
                if max_chapters not in (None, ""):
                    max_chapters_text = str(max_chapters).strip()
                    if isinstance(max_chapters, bool) or not re.fullmatch(
                        r"\d+", max_chapters_text
                    ):
                        raise ValueError(
                            "Số chương muốn chạy phải là số nguyên từ 1 trở lên"
                        )
                    max_chapters = int(max_chapters_text)
                    if max_chapters < 1:
                        raise ValueError(
                            "Số chương muốn chạy phải là số nguyên từ 1 trở lên"
                        )
                    config["max_chapters"] = max_chapters
                batch_runs = config.get("batch_runs")
                if batch_runs is not None:
                    batch_runs_text = str(batch_runs).strip()
                    if isinstance(batch_runs, bool) or not re.fullmatch(
                        r"\d+", batch_runs_text
                    ):
                        raise ValueError(
                            "Số lần chạy batch phải là số nguyên từ 0 trở lên"
                        )
                    config["batch_runs"] = int(batch_runs_text)
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
