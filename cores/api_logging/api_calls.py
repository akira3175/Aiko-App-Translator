"""Thread-safe JSONL logging for AI requests and responses."""

import json
from datetime import datetime
from pathlib import Path


def log_api_call(
    log_dir,
    lock,
    chapter_id: str,
    step: str,
    model: str,
    prompt: str,
    response: str,
    ok: bool = True,
    attachments=None,
):
    """Append one API call to the daily JSONL log."""
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    log_path = directory / f"{now:%Y-%m-%d}.jsonl"
    entry = {
        "ts": now.isoformat(timespec="seconds"),
        "chapter_id": chapter_id,
        "step": step,
        "model": model,
        "ok": ok,
        "prompt_len": len(prompt),
        "response_len": len(response),
        "prompt": prompt,
        "response": response,
        "attachments": attachments or [],
    }
    with lock:
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
