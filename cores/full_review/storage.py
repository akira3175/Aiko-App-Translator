"""JSON persistence for full-review results."""

import os
import threading

from cores.storage.project import load_json, save_json

_review_lock = threading.Lock()


def load_review(path):
    if not os.path.exists(path):
        return {}
    try:
        return load_json(path, {})
    except Exception:
        return {}


def save_review(data, path):
    with _review_lock:
        save_json(path, data, backup=True)


def load_manual_check(path):
    if not os.path.exists(path):
        return []
    try:
        data = load_json(path, [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_manual_check(data, path):
    save_json(path, data, backup=True)


def add_to_manual_check(chapter_id, path):
    data = load_manual_check(path)
    if chapter_id not in data:
        data.append(chapter_id)
        save_manual_check(data, path)
