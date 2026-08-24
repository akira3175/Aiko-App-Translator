"""Normalize and validate structured JSON responses from AI providers."""

import json
import re


def normalize_json_response(text):
    clean = str(text or "").strip()
    clean = re.sub(r"\s*###END###\s*$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"^```json\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    return clean


def parse_complete_json_object(text, *, strict=True):
    """Return the first complete JSON object and ignore surrounding prose."""
    clean = normalize_json_response(text)
    decoder = json.JSONDecoder(strict=strict)
    for match in re.finditer(r"\{", clean):
        try:
            parsed, _end = decoder.raw_decode(clean[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
