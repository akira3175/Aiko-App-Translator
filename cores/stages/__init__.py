"""Reusable stage helpers for the provider-independent pipeline."""

from cores.stages.outputs import (
    normalize_json_response,
    parse_complete_json_object,
    parse_json_object,
    parse_title_content,
)
from cores.stages.references import build_reference_documents
from cores.stages.transport import generate_for_stage
from cores.stages.runtime import (
    TRANSPORT_OVERRIDES,
    browser_lifecycle,
    generate_stage,
    stage_model_and_thinking,
    stage_provider,
    stage_transports,
)


__all__ = [
    "TRANSPORT_OVERRIDES",
    "build_reference_documents",
    "generate_for_stage",
    "browser_lifecycle",
    "generate_stage",
    "parse_json_object",
    "normalize_json_response",
    "parse_complete_json_object",
    "parse_title_content",
    "stage_model_and_thinking",
    "stage_provider",
    "stage_transports",
]
