"""Load and pair raw and translated chapters for full review."""

import os
import re

from cores.chapters.files import scan_md_dir


def _read_markdown(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def _split_markdown(text):
    title = ""
    content_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
        elif not stripped.startswith("![") and stripped:
            content_lines.append(stripped)
    return title, "\n".join(content_lines).strip()


def load_review_chapters(raw_dir, translated_dir):
    """Return paired chapter dictionaries and IDs without matching raw files."""
    chapters = []
    missing_raw = []
    for translated_path in scan_md_dir(translated_dir):
        chapter_id = os.path.splitext(os.path.basename(translated_path))[0]
        title, content = _split_markdown(_read_markdown(translated_path))
        raw_path = os.path.join(raw_dir, os.path.basename(translated_path))
        if os.path.exists(raw_path):
            raw_title, raw_content = _split_markdown(_read_markdown(raw_path))
        else:
            raw_title, raw_content = "", ""
            missing_raw.append(chapter_id)
        if content:
            chapters.append(
                {
                    "id": chapter_id,
                    "raw_title": raw_title,
                    "raw_content": raw_content,
                    "title_translation": title,
                    "translation": content,
                }
            )
    return chapters, missing_raw


def prepare_review_item(chapter, fallback_index=0):
    """Keep the complete raw/translation pair for equivalent comparison."""
    chapter_id = chapter.get("id", f"unknown_{fallback_index}")
    match = re.search(r"_c(\d+)_", chapter_id)
    chapter_number = int(match.group(1)) + 1 if match else fallback_index + 1
    content = chapter.get("translation", "")
    raw_content = chapter.get("raw_content", "")
    if not content.strip() or not raw_content.strip():
        return None
    return (
        chapter_id,
        chapter_number,
        chapter.get("raw_title", ""),
        raw_content,
        chapter.get("title_translation", ""),
        content,
    )
