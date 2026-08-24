"""Shared output parsers for translation pipeline stages."""

import re

from cores.json_output import normalize_json_response, parse_complete_json_object


def parse_title_content(text, stage):
    text = re.sub(r"\\###", "###", str(text or ""))
    if "###TITLE###" not in text or "###CONTENT###" not in text:
        raise ValueError(f"{stage} trả sai định dạng TITLE/CONTENT.")
    title_start = text.find("###TITLE###") + len("###TITLE###")
    content_start = text.find("###CONTENT###")
    title = text[title_start:content_start].strip()
    raw_content = text[content_start + len("###CONTENT###") :]
    end = raw_content.find("###END###")
    content = (raw_content[:end] if end >= 0 else raw_content).strip()
    placeholders = {
        "tiêu đề dịch", "nội dung dịch", "translated title", "translated content"
    }
    if not title or not content:
        raise ValueError(f"{stage} trả nội dung trống.")
    if title.strip("<>").lower() in placeholders or content.strip("<>").lower() in placeholders:
        raise ValueError(f"{stage} trả placeholder.")
    return title, content


def parse_json_object(text):
    clean = normalize_json_response(text)
    parsed = parse_complete_json_object(clean)
    return parsed if parsed is not None else {"raw": clean}
