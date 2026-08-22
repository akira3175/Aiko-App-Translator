"""Gemini API and browser integrations."""

import sys


for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from cores.gemini.runtime import GeminiRuntime, load_api_keys
from cores.gemini.client import (
    API_KEYS,
    call_gemini,
    current_gemini_api_key,
    get_client,
    runtime,
    switch_api_key,
)


__all__ = [
    "API_KEYS", "GeminiRuntime", "call_gemini", "current_gemini_api_key",
    "get_client", "load_api_keys", "runtime", "switch_api_key",
]
