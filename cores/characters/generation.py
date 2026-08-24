"""Provider-independent request and output validation for character analysis."""

import time

from cores.gemini import switch_api_key
from cores.config.runtime import option, stop_requested
from cores.stages import generate_stage
from cores.characters.parser import extract_character_block, parse_characters


TRANSPORT_OVERRIDES = {}


def call_character_analysis(prompt, *, provider, max_retries):
    for attempt in range(1, max_retries + 1):
        if stop_requested():
            raise InterruptedError("Đã dừng tác vụ hồ sơ nhân vật")
        try:
            response, _provider, _model = generate_stage(
                "characters",
                prompt,
                provider=provider,
                get_option=option,
                overrides=TRANSPORT_OVERRIDES,
            )
            return response.text.strip()
        except Exception as error:
            message = str(error)
            print(f"[API] Lỗi: {message[:120]}")
            if attempt >= max_retries:
                raise
            if provider == "gemini-api" and (
                "429" in message or "RESOURCE_EXHAUSTED" in message
            ):
                switch_api_key()
                delay = 10
            elif any(code in message for code in ("500", "502", "503", "504")):
                delay = 8
            else:
                delay = 3
            print(f"[API] Thử lại {attempt + 1}/{max_retries} sau {delay}s...")
            for _ in range(delay):
                if stop_requested():
                    raise InterruptedError("Đã dừng tác vụ hồ sơ nhân vật")
                time.sleep(1)
    return ""


def request_character_block(prompt, *, provider, max_retries):
    request_prompt = prompt
    for attempt in range(1, max_retries + 1):
        response = call_character_analysis(
            request_prompt, provider=provider, max_retries=max_retries
        )
        block = extract_character_block(response)
        if block and parse_characters(block):
            return block
        has_marker = "START" in response or "END" in response
        marker_state = "có marker nhưng thiếu header `## Tên nhân vật`" if has_marker else "thiếu marker"
        print(f"   Output không hợp lệ ({marker_state}, {len(response)} ký tự), lần {attempt}/{max_retries}.")
        if attempt < max_retries:
            request_prompt = prompt + """

LƯU Ý SỬA OUTPUT: Trả lại ít nhất một header `## Tên nhân vật`, đặt toàn bộ
nội dung giữa `###START###` và `###END###`, bọc trong một code block `markdown`.
Giữ nguyên dấu `##` trước tên nhân vật và không giải thích.
"""
    raise ValueError(
        f"{provider} trả output không có hồ sơ nhân vật hợp lệ sau {max_retries} lần; tiến độ chưa được tăng"
    )
