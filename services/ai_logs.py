"""Read, redact, write, and clear project AI logs."""

import json
import re
from dataclasses import dataclass
from datetime import datetime


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)


def redact(value):
    text = str(value or "")
    text = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", text)
    for pattern in _SECRET_PATTERNS[1:]:
        text = pattern.sub("[REDACTED]", text)
    return text


def append_r19(project_path, source, model, prompt, response, ok):
    log_dir = project_path / "logs"
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


def read(project_path, limit=200):
    log_dir = project_path / "logs"
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
                entry["prompt"] = redact(entry.get("prompt"))
                entry["response"] = redact(entry.get("response"))
                entry["attachments"] = [
                    {
                        "name": str(attachment.get("name", "Tệp đính kèm")),
                        "content": redact(attachment.get("content")),
                    }
                    for attachment in entry.get("attachments", [])
                    if isinstance(attachment, dict)
                ]
                entries.append(entry)
                if len(entries) >= limit:
                    return {"items": entries, "count": len(entries), "limit": limit}
    return {"items": entries, "count": len(entries), "limit": limit}


def clear(project_path):
    log_dir = project_path / "logs"
    removed = 0
    if log_dir.is_dir():
        for path in log_dir.glob("*.jsonl"):
            if path.is_file():
                path.unlink()
                removed += 1
    return {"ok": True, "removed": removed}


@dataclass(frozen=True)
class AiLogService:
    library: object

    @staticmethod
    def redact(value):
        return redact(value)

    @staticmethod
    def append_r19(project_path, source, model, prompt, response, ok):
        return append_r19(project_path, source, model, prompt, response, ok)

    def read(self, project_name, limit=200):
        return read(self.library.safe_project(project_name), limit)

    def clear(self, project_name):
        return clear(self.library.safe_project(project_name))
