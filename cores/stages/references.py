"""Build provider-neutral reference documents for translation stages."""

import os
from pathlib import Path

from cores.config import CHARACTERS_MD, PRONOUNS_JSON
from cores.postprocess.snapshots import build_characters_snapshot


def _read_and_remove(path, name, mime_type):
    if not path:
        return None
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
        return {"name": name, "mime_type": mime_type, "content": content} if content else None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def build_reference_documents(
    chapter,
    pronoun_context="",
    *,
    characters_file=CHARACTERS_MD,
    pronouns_file=PRONOUNS_JSON,
    include_translation=False,
):
    """Return relevant character and recent-pronoun documents without leaking temp files."""
    relevant = [chapter.get("title", ""), chapter.get("content", ""), pronoun_context]
    if include_translation:
        relevant.extend(
            [chapter.get("title_translation", ""), chapter.get("translation", "")]
        )
    character_path = build_characters_snapshot(
        characters_file, "\n".join(str(item or "") for item in relevant), max_characters=20
    )
    documents = (
        _read_and_remove(character_path, "characters.md", "text/markdown"),
    )
    return tuple(document for document in documents if document)
