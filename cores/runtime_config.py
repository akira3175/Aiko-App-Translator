"""Read named task options supplied by the local web application."""

import json
import os
from functools import lru_cache
from pathlib import Path


SETTINGS_FILE = Path(__file__).resolve().parents[1] / ".runtime" / "settings.json"


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


def stop_requested():
    """Return True when the web controller requested a clean stop."""
    path = os.environ.get("NOVEL_STOP_FILE", "")
    return bool(path) and os.path.exists(path)
