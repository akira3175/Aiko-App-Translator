"""Public API for R19 masking, translation, and restoration."""

from cores.r19.masking import (
    enabled,
    mask_contexts,
    mask_postprocess_contexts,
    prepare_chapters,
    prepare_postprocess_chapter,
    strip_previous_context,
    strip_r19_terms,
)
from cores.r19.restoration import (
    normalize_placeholder_variants,
    restore_results,
    restore_text,
)
from cores.r19.storage import load_terms, load_word_mappings, save_word_translation
from cores.r19.translation import (
    fragment_prompt,
    parse_fragment_translation,
    request_word_translation,
    translate_fragments,
)

__all__ = [
    "enabled",
    "fragment_prompt",
    "load_terms",
    "load_word_mappings",
    "mask_contexts",
    "mask_postprocess_contexts",
    "normalize_placeholder_variants",
    "parse_fragment_translation",
    "prepare_chapters",
    "prepare_postprocess_chapter",
    "request_word_translation",
    "restore_results",
    "restore_text",
    "save_word_translation",
    "strip_previous_context",
    "strip_r19_terms",
    "translate_fragments",
]
