"""Parse and validate character analysis responses (structured JSON + legacy Markdown)."""

import re

from cores.characters.store import FIELD_KEYS, chapter_key, normalize_chapter
from cores.json_output import parse_complete_json_object


def _restore_rendered_character_headings(text: str) -> str:
    """Restore Markdown headings stripped by ChatGPT's rendered HTML."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines):
            continue
        next_line = lines[next_index].strip().lstrip("#").strip().casefold()
        if next_line == "thông tin cơ bản":
            lines[index] = f"## {line.strip()}"
    for index, line in enumerate(lines):
        section = line.strip().lstrip("#").strip().casefold()
        if section in {"thông tin cơ bản", "xưng hô", "ghi chú dịch thuật"}:
            lines[index] = f"### {line.strip().lstrip('#').strip()}"
    return "\n".join(lines)


def extract_character_block(raw_response: str) -> str:
    cleaned = (raw_response or "").strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    cleaned = re.sub(r"(?m)^\\(?=#+\s*(?:(?:CHAR_)?START|(?:CHAR_)?END))", "", cleaned)
    start = re.search(r"(?im)^\s*#{3}\s*(?:CHAR_)?START\s*#{3}\s*$", cleaned)
    end = re.search(r"(?im)^\s*#{3}\s*(?:CHAR_)?END\s*#{3}\s*$", cleaned)
    if start and end and end.start() > start.end():
        return _restore_rendered_character_headings(
            cleaned[start.end() : end.start()].strip()
        )
    if re.search(r"(?m)^##\s+\S", cleaned):
        return cleaned
    restored = _restore_rendered_character_headings(cleaned)
    return restored if re.search(r"(?m)^##\s+\S", restored) else ""


def parse_characters(md_text: str) -> dict:
    characters = {}
    for block in re.split(r"\n(?=## )", md_text or ""):
        block = block.strip()
        if not block.startswith("## "):
            continue
        name = block.split("\n", 1)[0].lstrip("# ").strip()
        if name:
            characters[name] = block
    return characters


def merge_characters(existing_md: str, new_md_block: str) -> str:
    existing = parse_characters(existing_md)
    incoming = parse_characters(new_md_block)
    if not incoming:
        print("Không parse được nhân vật từ response mới.")
        return existing_md

    merged = dict(existing)
    added = updated = 0
    for name, block in incoming.items():
        if name not in merged:
            merged[name] = block
            added += 1
            continue
        old_block = merged[name]
        new_fields = {
            match.group(1).strip().lower()
            for match in re.finditer(r"(?m)^[-*+] \*\*(.+?)\*\*\s*:", block)
        }
        missing = []
        for line in old_block.splitlines():
            match = re.match(r"^[-*+] \*\*(.+?)\*\*\s*:", line)
            if match and match.group(1).strip().lower() not in new_fields:
                missing.append(line)
        if missing:
            block = block.rstrip() + "\n\n### Thông tin được bảo toàn\n" + "\n".join(missing)
        merged[name] = block
        updated += 1

    print(f"   Đã thêm {added} nhân vật mới, cập nhật {updated} nhân vật hiện có.")
    return "\n\n---\n\n".join(merged[name] for name in sorted(merged, key=str.lower))


# --------------------------------------------------------------------------- structured JSON extraction


def _strip_markers(raw_response: str) -> str:
    cleaned = str(raw_response or "").strip()
    cleaned = re.sub(r"^```(?:json|markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    cleaned = re.sub(r"(?m)^\\(?=#+\s*(?:(?:CHAR_)?START|(?:CHAR_)?END))", "", cleaned)
    start = re.search(r"(?im)^\s*#{3}\s*(?:CHAR_)?START\s*#{3}\s*$", cleaned)
    end = re.search(r"(?im)^\s*#{3}\s*(?:CHAR_)?END\s*#{3}\s*$", cleaned)
    if start and end and end.start() > start.end():
        return cleaned[start.end() : end.start()].strip()
    return cleaned


def _allowed_set(allowed_chapters):
    result = set()
    for item in allowed_chapters or ():
        raw = str(item or "").strip()
        if not raw:
            continue
        if chapter_key(raw):
            result.add(normalize_chapter(raw))
        else:
            result.add(raw.lower())
    return result


def _chapter_in_allowed(value, allowed):
    raw = str(value or "").strip()
    if not raw:
        return False
    if chapter_key(raw):
        return normalize_chapter(raw) in allowed
    return raw.lower() in allowed


def extract_character_payload(raw_response: str, allowed_chapters=None):
    """Extract and validate a structured AI character update payload.

    Returns ``(payload, error_message)``. ``payload`` is ``None`` when invalid.
    """
    inner = _strip_markers(raw_response)
    parsed = parse_complete_json_object(inner)
    if parsed is None:
        parsed = parse_complete_json_object(raw_response)
    if not isinstance(parsed, dict):
        return None, "không tìm thấy đối tượng JSON hợp lệ"
    items = parsed.get("characters")
    if not isinstance(items, list):
        return None, 'thiếu danh sách "characters" trong JSON'

    allowed = _allowed_set(allowed_chapters) if allowed_chapters is not None else None
    valid_characters = 0
    total_updates_or_events = 0
    valid_updates_or_events = 0

    for item in items:
        if not isinstance(item, dict):
            return None, 'phần tử trong "characters" không phải object'
        name = str(item.get("name") or "").strip()
        cid = str(item.get("id") or "").strip()
        if not name and not cid:
            return None, "có nhân vật thiếu cả name và id"
        updates = item.get("updates", [])
        events = item.get("events", [])
        if updates is not None and not isinstance(updates, list):
            return None, f'trường "updates" của "{name or cid}" phải là danh sách'
        if events is not None and not isinstance(events, list):
            return None, f'trường "events" của "{name or cid}" phải là danh sách'
        valid_characters += 1
        for update in updates or []:
            if not isinstance(update, dict):
                continue
            total_updates_or_events += 1
            field = str(update.get("field") or "").strip()
            value = str(update.get("value") or "").strip()
            chapter = update.get("chapter")
            if field in FIELD_KEYS and value and (
                allowed is None or _chapter_in_allowed(chapter, allowed)
            ):
                valid_updates_or_events += 1
        for event in events or []:
            if not isinstance(event, dict):
                continue
            total_updates_or_events += 1
            text = str(event.get("text") or "").strip()
            chapter = event.get("chapter")
            if text and (allowed is None or _chapter_in_allowed(chapter, allowed)):
                valid_updates_or_events += 1

    if total_updates_or_events > 0 and valid_updates_or_events == 0:
        return (
            None,
            "tất cả updates/events đều sai field hoặc mã chương không nằm trong batch hiện tại",
        )
    if items and valid_characters == 0:
        return None, "không có nhân vật hợp lệ nào trong JSON"
    return parsed, ""
