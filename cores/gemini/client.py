"""Configured Gemini API client and persistent key rotation."""

from google import genai

from cores.storage.data_paths import (
    GEMINI_API_KEYS_FILE,
    GEMINI_API_KEY_STATE_FILE,
    ensure_user_data_migrated,
)
from cores.gemini.runtime import GeminiRuntime, load_api_keys


ensure_user_data_migrated()
API_KEYS = load_api_keys(GEMINI_API_KEYS_FILE)
runtime = GeminiRuntime(API_KEYS, GEMINI_API_KEY_STATE_FILE, genai.Client)
print(f"🔑 Bắt đầu với API key số {runtime.current_key_index + 1}/{len(API_KEYS)}")


def get_client():
    return runtime.get_client()


def switch_api_key():
    return runtime.switch()


def current_gemini_api_key():
    return runtime.current_key


def call_gemini(
    prompt,
    model,
    max_output_tokens=None,
    system_instruction=None,
    as_chat_parts=False,
    extra_parts=None,
    character_document=None,
    pronoun_document=None,
    thinking_level=None,
):
    return runtime.generate(
        prompt,
        model,
        max_output_tokens=max_output_tokens,
        system_instruction=system_instruction,
        as_chat_parts=as_chat_parts,
        extra_parts=extra_parts,
        character_document=character_document,
        pronoun_document=pronoun_document,
        thinking_level=thinking_level,
    )
