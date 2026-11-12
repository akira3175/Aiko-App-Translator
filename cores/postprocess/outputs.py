"""Separate polished prose from optional structured pronoun output."""

import json
import re

from cores.json_output import normalize_json_response
from cores.pronouns.extraction import validate_pronoun_payload
from cores.stages.outputs import parse_title_content


_MARKER = re.compile(r"(###(?:TITLE|CONTENT|PRONOUNS|END)###)")


def parse_polish_output(text):
    """Return (title, content, payload); invalid/missing payload is None.

    An end marker is required even when optional JSON is invalid.
    Only a complete, schema-valid PRONOUNS section may replace stored history.
    """
    text = re.sub(r"\\###", "###", str(text or ""))
    markers = list(_MARKER.finditer(text))
    names = [match.group(1) for match in markers]
    if names[:2] != ["###TITLE###", "###CONTENT###"]:
        raise ValueError("Hiệu đính trả sai thứ tự TITLE/CONTENT.")
    if names.count("###TITLE###") != 1 or names.count("###CONTENT###") != 1:
        raise ValueError("Hiệu đính trả marker TITLE/CONTENT trùng lặp.")
    if names.count("###END###") != 1 or names[-1] != "###END###":
        raise ValueError("Hiệu đính chưa hoàn tất hoặc sai thứ tự: thiếu ###END### hợp lệ.")
    title = text[markers[0].end():markers[1].start()].strip()
    content_end = markers[2].start() if len(markers) > 2 else len(text)
    content = text[markers[1].end():content_end].strip()
    title, content = parse_title_content(
        f"###TITLE###\n{title}\n###CONTENT###\n{content}\n###END###", "Hiệu đính"
    )
    payload = None
    if names[2:] == ["###PRONOUNS###", "###END###"]:
        raw = text[markers[2].end():markers[3].start()].strip()
        try:
            parsed = json.loads(normalize_json_response(raw))
            validate_pronoun_payload(parsed)
            payload = parsed
        except (ValueError, TypeError):
            pass
    return title, content, payload
