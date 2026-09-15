"""Provider-independent glossary generation."""

import time

from cores.gemini import switch_api_key
from cores.context.prompts import build_glossary_prompt
from cores.config.runtime import int_option, option
from cores.stages import (
    browser_lifecycle as stage_browser_lifecycle,
    generate_stage,
    stage_model_and_thinking,
    stage_provider,
    stage_transports,
)


TRANSPORT_OVERRIDES = {}


def context_provider():
    return stage_provider("context", get_option=option)


def context_model_and_thinking(provider):
    return stage_model_and_thinking("context", provider, get_option=option)


def context_transports():
    return stage_transports(TRANSPORT_OVERRIDES)


def browser_lifecycle(provider):
    return stage_browser_lifecycle(provider)


def generate_glossary(chapters, old_glossary, instructions=None):
    prompt = build_glossary_prompt(chapters, old_glossary, instructions)
    if not prompt:
        print("⚠️ Batch này không có nội dung, bỏ qua.")
        return ""
    provider = context_provider()
    model, thinking = context_model_and_thinking(provider)
    retries = int_option("context_retries", 3, minimum=1)
    for attempt in range(1, retries + 1):
        try:
            print(f"📤 Gửi {provider} bằng {model} (lần {attempt}/{retries})...")
            response = generate_stage(
                "context",
                prompt,
                provider=provider,
                get_option=option,
                overrides=TRANSPORT_OVERRIDES,
            )[0].text.strip()
            if "###START###" in response and "###END###" in response:
                return response
            print("⚠️ Kết quả thiếu marker START/END.")
        except Exception as error:
            print(f"⚠️ Lỗi tạo Context qua {provider}: {error}")
            if provider == "gemini-api" and (
                "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)
            ):
                switch_api_key()
        if attempt < retries:
            time.sleep(5)
    raise ValueError(f"{provider} không trả về glossary hợp lệ sau {retries} lần thử")
