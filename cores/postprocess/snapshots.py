"""Reference snapshots used by translation and post-processing stages."""

import json
import os
import re
import tempfile
import unicodedata

from cores.pronouns import load_pronouns


def character_blocks(markdown):
    matches = list(re.finditer(r"(?m)^## (?!#)(.+?)\s*$", markdown or ""))
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[match.start() : end].strip("\n- ")
        if block:
            blocks.append((match.group(1).strip(), block))
    return blocks


def character_aliases(header, block):
    aliases = [part.strip() for part in re.split(r"\s+/\s+", header) if part.strip()]
    field_pattern = re.compile(
        r"(?im)^- \*\*(?:Tên gốc|Ten goc|Biệt danh / Danh hiệu|Biet danh / Danh hieu)\*\*:\s*(.+)$"
    )
    for value in field_pattern.findall(block):
        for part in re.split(r"\s*/\s*|\s*,\s*", value):
            part = part.strip(" -")
            if not part:
                continue
            aliases.append(part)
            aliases.extend(item.strip() for item in re.findall(r"\(([^()]+)\)", part))
            outside = re.sub(r"\([^()]+\)", "", part).strip()
            if outside:
                aliases.append(outside)
    return list(dict.fromkeys(alias for alias in aliases if alias))


def character_alias_score(alias, searchable):
    normalized = unicodedata.normalize("NFKC", alias).casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return 0
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]", normalized):
        return searchable.count(normalized)
    return len(
        re.findall(rf"(?<!\w){re.escape(normalized)}(?!\w)", searchable)
    )


def build_characters_snapshot(characters_file, relevant_text, max_characters=20):
    """Create a temporary Markdown file containing only relevant character profiles."""
    if not os.path.exists(characters_file):
        return None
    try:
        with open(characters_file, "r", encoding="utf-8") as file:
            markdown = file.read()
    except OSError:
        return None

    blocks = character_blocks(markdown)
    if not blocks:
        return None

    searchable = unicodedata.normalize("NFKC", relevant_text or "").casefold()
    searchable = re.sub(r"\s+", " ", searchable)
    ranked = []
    for order, (header, block) in enumerate(blocks):
        aliases = character_aliases(header, block)
        score = sum(
            min(character_alias_score(alias, searchable), 5)
            for alias in aliases
        )
        if score:
            ranked.append((score, -order, header, block))

    if not ranked:
        return None
    ranked.sort(reverse=True)
    selected = ranked[:max_characters]
    selected.sort(key=lambda item: -item[1])
    snapshot = "# Hồ Sơ Nhân Vật Liên Quan\n\n" + "\n\n---\n\n".join(
        item[3] for item in selected
    )
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_characters_snapshot.md",
        encoding="utf-8",
        delete=False,
    )
    tmp.write(snapshot.rstrip() + "\n")
    tmp.close()
    print(
        f"[UPLOAD] Characters snapshot: {len(selected)}/{len(blocks)} hồ sơ -> {tmp.name}"
    )
    return tmp.name


def build_pronouns_snapshot(pronouns_file, n_chapters=50):
    """
    Lọc pronouns.json: chỉ giữ N chapter_number gần nhất.
    Ghi ra file tam va tra ve duong dan file tam do.
    Tra ve None neu memory rong.
    """
    memory = load_pronouns(pronouns_file)
    if not memory:
        return None

    all_chapters = set()
    for data in memory.values():
        for entry in data.get("timeline", []):
            ch = entry.get("chapter_number", 0)
            if ch:
                all_chapters.add(ch)

    if not all_chapters:
        return None

    recent_chapters = set(sorted(all_chapters, reverse=True)[:n_chapters])

    filtered = {}
    for key_str, data in memory.items():
        tl = [
            e
            for e in data.get("timeline", [])
            if e.get("chapter_number", 0) in recent_chapters
        ]
        if tl:
            filtered[key_str] = {
                "characters": data.get("characters", []),
                "timeline": tl,
                "locked": bool(data.get("locked", False)),
            }

    if not filtered:
        return None

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_pronouns_snapshot.json", encoding="utf-8", delete=False
    )
    json.dump(filtered, tmp, ensure_ascii=False, indent=2)
    tmp.write("\n")
    tmp.close()
    print(
        f"[UPLOAD] Pronouns snapshot: {len(filtered)} cap, {n_chapters} chuong gan nhat -> {tmp.name}"
    )
    return tmp.name
