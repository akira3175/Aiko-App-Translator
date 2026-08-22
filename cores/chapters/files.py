"""Read, scan, and inspect Markdown chapter files."""

import os
import re
import unicodedata
import sys


for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def sort_key_md(filename):
    match = re.match(r"v(\d+)_c(\d+)_s(\d+)\.md$", os.path.basename(filename))
    if match:
        return tuple(int(value) for value in match.groups())
    return (0, 0, 0)


def scan_md_dir(directory):
    if not os.path.exists(directory):
        return []
    files = [name for name in os.listdir(directory) if name.endswith(".md")]
    files.sort(key=sort_key_md)
    return [os.path.join(directory, name) for name in files]


def is_translated(chapter_id, translated_dir):
    path = os.path.join(translated_dir, f"{chapter_id}.md")
    return os.path.exists(path) and os.path.getsize(path) > 10


def load_md_chapter(filepath):
    with open(filepath, "r", encoding="utf-8") as handle:
        raw = handle.read()
    chapter_id = os.path.splitext(os.path.basename(filepath))[0]
    title = ""
    elements = []
    title_found = False
    for block in (block.strip() for block in raw.split("\n\n") if block.strip()):
        if not title_found and block.startswith("# "):
            title = block[2:].strip()
            title_found = True
            continue
        element_type = "image" if block.startswith("![") else "text"
        elements.append({"type": element_type, "content": block})
    return {
        "id": chapter_id,
        "title": title,
        "content": "\n\n".join(element["content"] for element in elements if element["type"] == "text"),
        "title_translation": "",
        "translation": "",
        "_elements": elements,
    }


def get_translated_title(chapter_id, translated_dir):
    path = os.path.join(translated_dir, f"{chapter_id}.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("# "):
                return line[2:]
    return ""


def save_translated_md(raw_filepath, translated_dir, title, content):
    """Save translated text while restoring image blocks from the raw chapter."""
    os.makedirs(translated_dir, exist_ok=True)
    with open(raw_filepath, "r", encoding="utf-8") as handle:
        blocks = [block.strip() for block in handle.read().split("\n\n") if block.strip()]

    elements = []
    title_found = False
    for block in blocks:
        if not title_found and block.startswith("# "):
            title_found = True
            continue
        elements.append(
            {"type": "image" if block.startswith("![") else "text", "content": block}
        )

    translated = [paragraph.strip() for paragraph in content.split("\n") if paragraph.strip()]
    output = [f"# {title}", ""]
    translated_index = 0
    for element in elements:
        if element["type"] == "image":
            output.extend((element["content"], ""))
        elif translated_index < len(translated):
            output.extend((translated[translated_index], ""))
            translated_index += 1
    while translated_index < len(translated):
        output.extend((translated[translated_index], ""))
        translated_index += 1

    output_path = os.path.join(translated_dir, os.path.basename(raw_filepath))
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(output))
    return output_path


def export_recent_translations(
    raw_dir,
    translated_dir,
    txt_path,
    n=3,
    target_chapter_id=None,
):
    raw_files = scan_md_dir(raw_dir)
    translated_files = scan_md_dir(translated_dir)
    print(f"📊 Tổng số chương raw: {len(raw_files)}")
    print(f"✅ Số chương đã dịch: {len(translated_files)}")

    if target_chapter_id and translated_files:
        target_key = sort_key_md(target_chapter_id + ".md")
        translated_files = [
            path
            for path in translated_files
            if sort_key_md(os.path.basename(path)) < target_key
        ]
    recent = (
        translated_files[-n:]
        if n and len(translated_files) >= n
        else (translated_files if n else [])
    )
    if not recent:
        print("⚠️ Không tìm thấy chương nào đã dịch!")
        return

    with open(txt_path, "w", encoding="utf-8") as output:
        for path in recent:
            with open(path, "r", encoding="utf-8") as chapter:
                output.write(chapter.read().strip() + "\n\n\n\n\n")
    names = [os.path.basename(path) for path in recent]
    print(f"📂 Đã xuất {len(recent)} chương ngữ cảnh ra: {txt_path} ({', '.join(names)})")


def has_chinese(text):
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ebef\U00030000-\U000323af]", text))


def has_korean(text):
    return bool(re.search(r"[\uac00-\ud7af]", text))


def has_thai(text):
    return bool(re.search(r"[\u0e00-\u0e7f]", text))


KAOMOJI_RE = re.compile(r"[（(]([^()（）\r\n]{1,40})[)）]")


def _without_kaomoji(text):
    def replace(match):
        body = match.group(1)
        symbol_count = sum(
            unicodedata.category(character)[0] in {"P", "S"}
            for character in body
        )
        return " " if symbol_count >= 2 else match.group(0)

    return KAOMOJI_RE.sub(replace, str(text or ""))


def has_foreign(text):
    checked = _without_kaomoji(text)
    return has_chinese(checked) or has_korean(checked) or has_thai(checked)
