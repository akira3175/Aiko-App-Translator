"""Pronoun-memory storage, extraction, matching, and prompt context."""

import sys


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


from cores.pronouns.context import format_pronoun_context
from cores.pronouns.extraction import (
    extract_pronouns_from_translation,
    update_pronoun_memory,
)
from cores.pronouns.matching import _name_matches_glossary
from cores.pronouns.normalize import (
    NameResolver,
    clean_pronoun,
    group_directions,
    load_character_roster,
    resolve_direction,
)
from cores.pronouns.storage import load_pronouns, save_pronouns


__all__ = [
    "NameResolver",
    "clean_pronoun",
    "extract_pronouns_from_translation",
    "format_pronoun_context",
    "group_directions",
    "load_character_roster",
    "load_pronouns",
    "resolve_direction",
    "save_pronouns",
    "update_pronoun_memory",
]
