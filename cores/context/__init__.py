"""Project context and glossary selection for the 1.0 JSON/TXT format."""

from cores.context.glossary import filter_glossary, glossary_source_is_relevant
from cores.context.selection import find_glossary_targets
from cores.context.storage import load_context_text
from cores.context.merge import merge_context


__all__ = [
    "filter_glossary",
    "find_glossary_targets",
    "glossary_source_is_relevant",
    "load_context_text",
    "merge_context",
]
