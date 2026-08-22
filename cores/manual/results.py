"""Parse manually supplied translation results."""

import re


def _is_placeholder(value, placeholders):
    normalized = value.strip("<>").strip().lower()
    return normalized in {
        placeholder.strip("<>").strip().lower() for placeholder in placeholders
    }


def parse_manual_result_text(text):
    text = re.sub(r"\\\#\\\#\\\#", "###", str(text or "").strip())
    if "###TITLE###" not in text or "###CONTENT###" not in text:
        raise ValueError("Kết quả cần đủ ###TITLE### và ###CONTENT###.")
    title_start = text.find("###TITLE###") + len("###TITLE###")
    content_start = text.find("###CONTENT###")
    title = text[title_start:content_start].strip()
    raw_content = text[content_start + len("###CONTENT###") :]
    end = raw_content.find("###END###")
    content = (raw_content[:end] if end >= 0 else raw_content).strip()
    if not title or not content:
        raise ValueError("Tiêu đề hoặc nội dung dịch đang trống.")
    if _is_placeholder(title, ("<tiêu đề dịch>", "<translated title>")):
        raise ValueError("Tiêu đề vẫn là placeholder.")
    if _is_placeholder(content, ("<nội dung dịch>", "<translated content>")):
        raise ValueError("Nội dung vẫn là placeholder.")
    return title, content
