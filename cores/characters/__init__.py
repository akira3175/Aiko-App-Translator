"""Character-profile generation and structured storage package."""

from cores.characters.store import (
    load_document,
    merge_ai_updates,
    render_batch_snapshot,
    render_markdown,
    render_snapshot,
    restore_backup,
    save_document,
)

__all__ = [
    "build_character_prompt",
    "load_document",
    "merge_ai_updates",
    "render_batch_snapshot",
    "render_markdown",
    "render_snapshot",
    "restore_backup",
    "run_character_generation",
    "save_document",
]


def __getattr__(name):
    if name == "build_character_prompt":
        from cores.characters.prompt import build_character_prompt

        return build_character_prompt
    if name == "run_character_generation":
        from cores.characters.workflow import run_character_generation

        return run_character_generation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
