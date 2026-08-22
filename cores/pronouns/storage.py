"""Persistence for pronoun memory."""

import os

from cores.storage.project import load_json, save_json


def load_pronouns(file_path):
    """Tải bộ nhớ xưng hô từ file."""
    if not os.path.exists(file_path):
        return {}
    return load_json(file_path, {})


def save_pronouns(data, file_path):
    """Lưu bộ nhớ xưng hô vào file."""
    save_json(file_path, data)
