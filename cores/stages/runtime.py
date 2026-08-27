"""Shared provider, model, transport, and browser resolution for AI stages."""

from cores.browser import (
    close_chatgpt_driver,
    close_gemini_driver,
    close_ai_studio_driver,
    generate_content_with_chatgpt,
    generate_content_with_selenium,
    generate_content_with_ai_studio,
    setup_chatgpt_browser,
    setup_gemini_browser,
    setup_ai_studio_browser,
)
from cores.gemini import call_gemini
from providers.openai_client import call_gpt_api
from cores.config.runtime import option
from cores.stages.transport import generate_for_stage


MODEL_DEFAULTS = {
    "gemini-api": {
        "translate": ("translate_model", "gemini-flash-latest"),
        "polish": ("polish_model", "gemini-flash-latest"),
        "pronouns": ("pronoun_model", "gemini-flash-lite-latest"),
        "review": ("review_bg_model", "gemini-flash-lite-latest"),
        "context": ("context_model", "gemini-flash-latest"),
        "characters": ("character_model", "gemini-flash-latest"),
    },
    "gemini-web": {},
    "google-ai-studio-web": {},
    "openai-api": {
        "translate": ("gpt_api_translate_model", "gpt-5.6-luna"),
        "polish": ("gpt_api_polish_model", "gpt-5.6-terra"),
        "pronouns": ("gpt_api_pronoun_model", "gpt-5.6-terra"),
        "review": ("gpt_api_review_model", "gpt-5.6-terra"),
        "context": ("gpt_api_translate_model", "gpt-5.6-luna"),
        "characters": ("gpt_api_translate_model", "gpt-5.6-luna"),
    },
    "chatgpt-web": {},
}


TRANSPORT_OVERRIDES = {}

STAGE_LABELS = {
    "translate": "Dịch",
    "polish": "Hiệu đính",
    "pronouns": "Xưng hô",
    "review": "Review",
    "context": "Context",
    "characters": "Hồ sơ nhân vật",
}
PROVIDER_LABELS = {
    "gemini-api": "Gemini API",
    "gemini-web": "Gemini Web",
    "google-ai-studio-web": "Google AI Studio Web",
    "openai-api": "OpenAI API",
    "chatgpt-web": "ChatGPT Web",
}


def stage_provider(stage, *, get_option=option, default="gemini-api"):
    return str(get_option(f"{stage}_provider", default)).strip().lower()


def stage_model_and_thinking(stage, provider, *, get_option=option):
    model = str(get_option(f"{stage}_stage_model", "")).strip()
    thinking = str(get_option(f"{stage}_stage_thinking", "")).strip()
    if provider == "gemini-api":
        key, default = MODEL_DEFAULTS[provider][stage]
        return (
            model or str(get_option(key, default)),
            thinking or str(get_option("gemini_api_thinking", "high")),
        )
    if provider == "gemini-web":
        return (
            model or str(get_option("gemini_web_model", "pro")),
            thinking or str(get_option("gemini_thinking", "extended")),
        )
    if provider == "google-ai-studio-web":
        model_key, model_default = {
            "pronouns": ("ai_studio_pronoun_model", "gemini-flash-lite-latest"),
            "review": ("ai_studio_review_model", "gemini-flash-lite-latest"),
        }.get(stage, ("ai_studio_model", "gemini-flash-latest"))
        return (
            model or str(get_option(model_key, model_default)),
            thinking or str(get_option("ai_studio_thinking", "high")),
        )
    if provider == "openai-api":
        key, default = MODEL_DEFAULTS[provider][stage]
        effort_key = {
            "translate": "gpt_api_translate_effort",
            "review": "gpt_api_review_effort",
            "context": "gpt_api_translate_effort",
            "characters": "gpt_api_translate_effort",
        }.get(stage, "gpt_api_polish_effort")
        return (
            model or str(get_option(key, default)),
            thinking or str(get_option(effort_key, "high")),
        )
    if provider == "chatgpt-web":
        return (
            model or str(get_option("chatgpt_model", "gpt-5.6 sol")),
            thinking or str(get_option("chatgpt_thinking", "cao")),
        )
    raise ValueError(f"Provider không hợp lệ cho công đoạn {stage}: {provider}")


def stage_transports(overrides=None):
    transports = {
        "gemini-api": call_gemini,
        "gemini-web": generate_content_with_selenium,
        "google-ai-studio-web": generate_content_with_ai_studio,
        "openai-api": call_gpt_api,
        "chatgpt-web": generate_content_with_chatgpt,
    }
    transports.update(overrides or {})
    return transports


def generate_stage(
    stage, prompt, *, provider=None, get_option=option, overrides=None, attachments=()
):
    provider = provider or stage_provider(stage, get_option=get_option)
    model, thinking = stage_model_and_thinking(
        stage, provider, get_option=get_option
    )
    print(
        f"[AI] {STAGE_LABELS.get(stage, stage)} · "
        f"{PROVIDER_LABELS.get(provider, provider)} · {model}",
        flush=True,
    )
    response = generate_for_stage(
        provider,
        "glossary" if stage == "context" else stage,
        prompt,
        model,
        thinking,
        stage_transports(overrides),
        attachments,
    )
    return response, provider, model


def browser_lifecycle(provider):
    if provider == "gemini-web":
        return setup_gemini_browser, close_gemini_driver
    if provider == "google-ai-studio-web":
        return setup_ai_studio_browser, close_ai_studio_driver
    if provider == "chatgpt-web":
        return setup_chatgpt_browser, close_chatgpt_driver
    return None, None
