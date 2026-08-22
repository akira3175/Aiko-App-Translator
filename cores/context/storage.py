"""Render context.json and glossary.txt as translation prompt context."""

import os

from cores.context.glossary import filter_glossary
from cores.storage.project import load_context


def load_context_text(file_path, raw_text=None):
    if not os.path.exists(file_path):
        return ""
    context = load_context(os.path.dirname(file_path))
    parts = []
    glossary = str(context.get("glossary", "") or "")
    if raw_text is not None:
        glossary = filter_glossary(glossary, raw_text)
    if glossary:
        parts.append("Thuật ngữ:\n" + glossary)
    if context.get("style_notes"):
        parts.append("Ghi chú văn phong:\n" + context["style_notes"])
    if context.get("previous_translations"):
        parts.append(
            "Bản dịch tham khảo:\n" + "\n".join(context["previous_translations"])
        )
    return "\n\n".join(parts)
