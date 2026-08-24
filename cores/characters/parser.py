"""Parse and merge Markdown character profiles."""

import re


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
        if section in {"thông tin cơ bản", "ghi chú dịch thuật"}:
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
