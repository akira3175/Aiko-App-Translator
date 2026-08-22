"""Parse and merge Markdown character profiles."""

import re


def extract_character_block(raw_response: str) -> str:
    cleaned = (raw_response or "").strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    cleaned = re.sub(r"(?m)^\\(?=#+\s*(?:CHAR_START|CHAR_END))", "", cleaned)
    start = re.search(r"(?im)^\s*#{3}\s*CHAR_START\s*#{3}\s*$", cleaned)
    end = re.search(r"(?im)^\s*#{3}\s*CHAR_END\s*#{3}\s*$", cleaned)
    if start and end and end.start() > start.end():
        return cleaned[start.end() : end.start()].strip()
    if re.search(r"(?m)^##\s+\S", cleaned):
        return cleaned
    return ""


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
            for match in re.finditer(r"(?m)^- \*\*(.+?)\*\*\s*:", block)
        }
        missing = []
        for line in old_block.splitlines():
            match = re.match(r"^- \*\*(.+?)\*\*\s*:", line)
            if match and match.group(1).strip().lower() not in new_fields:
                missing.append(line)
        if missing:
            block = block.rstrip() + "\n\n### Thông tin được bảo toàn\n" + "\n".join(missing)
        merged[name] = block
        updated += 1

    print(f"   Đã thêm {added} nhân vật mới, cập nhật {updated} nhân vật hiện có.")
    return "\n\n---\n\n".join(merged[name] for name in sorted(merged, key=str.lower))
