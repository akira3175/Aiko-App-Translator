"""Persistence for user-managed Gemini API keys."""

import json
import os

from cores.gemini.key_manager import GeminiKeyManager


def payload(keys_file, state_file):
    try:
        keys = [
            line.strip()
            for line in keys_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except FileNotFoundError:
        keys = []
    active_index = 0
    try:
        fingerprint = json.loads(state_file.read_text(encoding="utf-8")).get(
            "current_key_fingerprint", ""
        )
        active_index = next(
            (
                index
                for index, key in enumerate(keys)
                if GeminiKeyManager.fingerprint(key) == fingerprint
            ),
            0,
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {"keys": keys, "count": len(keys), "active_index": active_index}


def save(request, keys_file, state_file):
    keys = request.get("keys")
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
    keys_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = keys_file.with_suffix(".tmp")
    temporary.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    os.replace(temporary, keys_file)
    return {**payload(keys_file, state_file), "count": len(cleaned)}


def set_active(request, keys_file, state_file):
    keys = payload(keys_file, state_file)["keys"]
    try:
        index = int(request.get("active_index"))
    except (TypeError, ValueError):
        raise ValueError("Vị trí API key không hợp lệ") from None
    if index < 0 or index >= len(keys):
        raise ValueError("API key đã chọn không tồn tại")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"current_key_fingerprint": GeminiKeyManager.fingerprint(keys[index])},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, state_file)
    return {"ok": True, "active_index": index, "count": len(keys)}
