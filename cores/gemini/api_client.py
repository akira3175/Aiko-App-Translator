"""Gemini Generate Content request construction."""

from google.genai import types

from cores.config.runtime import option


SAFETY_OFF = [
    types.SafetySetting(
        category=category,
        threshold=types.HarmBlockThreshold.OFF,
    )
    for category in (
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]


def generate_content(
    client,
    prompt,
    model,
    max_output_tokens=None,
    system_instruction=None,
    as_chat_parts=False,
    extra_parts=None,
    thinking_level=None,
):
    """Build and execute one Gemini Generate Content request."""
    config = {"safety_settings": SAFETY_OFF}
    thinking_level = str(
        thinking_level or option("gemini_api_thinking", "high")
    ).strip().lower()
    if thinking_level == "off":
        config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    elif thinking_level != "auto":
        config["thinking_config"] = types.ThinkingConfig(
            thinking_level=thinking_level
        )

    configured_max_tokens = option("gemini_api_max_output_tokens", "")
    if configured_max_tokens not in (None, ""):
        config["max_output_tokens"] = int(configured_max_tokens)
    elif max_output_tokens:
        config["max_output_tokens"] = max_output_tokens
    if system_instruction:
        config["system_instruction"] = system_instruction

    if as_chat_parts:
        parts = [{"text": prompt}, *(extra_parts or [])]
        contents = [{"role": "user", "parts": parts}]
    else:
        contents = [prompt]

    print(
        f"📤 Đã gửi prompt ({len(prompt)} ký tự). "
        "Đang chờ Gemini phản hồi...",
        flush=True,
    )
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(**config),
    )
    try:
        text = response.text
        if not text.strip():
            print(
                "\n[DEBUG GEMINI] response.text rỗng! "
                f"Chi tiết response:\n{response}\n[END DEBUG]\n"
            )
        return text
    except Exception as error:
        print(f"\n[DEBUG GEMINI] Không đọc được response.text: {error}")
        print(f"Chi tiết response:\n{response}\n[END DEBUG]\n")
        return ""
