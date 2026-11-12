"""Persistence for pronoun memory."""

import os
from contextlib import contextmanager
from pathlib import Path

from cores.storage.project import load_json, save_json


@contextmanager
def _write_lock(file_path):
    """Serialize writers across the UI server and translation processes."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep this sidecar in place: deleting it can split concurrent lock holders.
    with open(path.with_name(path.name + ".lock"), "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def edit_pronouns(file_path, *, backup=False):
    """Read the latest memory and commit edits under one interprocess lock."""
    with _write_lock(file_path):
        data = load_pronouns(file_path)
        if not isinstance(data, dict):
            raise ValueError("pronouns.json không hợp lệ")
        yield data
        save_json(file_path, data, backup=backup)


def load_pronouns(file_path):
    """Tải bộ nhớ xưng hô từ file."""
    if not os.path.exists(file_path):
        return {}
    return load_json(file_path, {})


def save_pronouns(data, file_path):
    """Lưu bộ nhớ xưng hô vào file."""
    with _write_lock(file_path):
        save_json(file_path, data)
