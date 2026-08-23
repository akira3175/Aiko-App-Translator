"""Read named task options supplied by the local web application."""

import json
import os
from functools import lru_cache
from pathlib import Path

from cores.config.project_paths import USER_DATA_ROOT

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = USER_DATA_ROOT / "settings.json"
LEGACY_SETTINGS_FILE = ROOT / ".runtime" / "settings.json"


def ensure_settings_migrated():
    """Move the current installation's settings to shared per-user storage once."""
    if SETTINGS_FILE.is_file():
        return None
    if not LEGACY_SETTINGS_FILE.is_file():
        return None
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.replace(LEGACY_SETTINGS_FILE, SETTINGS_FILE)
    task_config.cache_clear()
    return LEGACY_SETTINGS_FILE


def web_mode():
    return os.environ.get("NOVEL_WEB_MODE") == "1"


@lru_cache(maxsize=1)
def task_config():
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    try:
        value = json.loads(os.environ.get("NOVEL_WEB_CONFIG", "{}"))
    except json.JSONDecodeError:
        value = {}
    if not isinstance(value, dict):
        value = {}
    return {**saved, **value}


def option(name, default=None):
    return task_config().get(name, default)


def int_option(name, default=None, minimum=None):
    value = option(name, default)
    if value in (None, ""):
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(value, minimum) if minimum is not None else value


def bool_option(name, default=False):
    value = option(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def chapter_limit(default=1):
    """Maximum chapters for one web run; a blank value means no limit."""
    if not web_mode():
        return None
    value = option("max_chapters", None)
    if value in (None, ""):
        return None if value == "" or bool_option("run_until_complete", False) else default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def stop_requested():
    """Return True when the web controller requested a clean stop."""
    path = os.environ.get("NOVEL_STOP_FILE", "")
    return bool(path) and os.path.exists(path)
