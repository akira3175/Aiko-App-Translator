"""Provider registry and compatibility bridge for the stage-based pipeline."""

from providers.base import ProviderCapabilities
from providers.chatgpt_web import ChatGptWebProvider
from providers.gemini_api import GeminiApiProvider
from providers.gemini_web import GeminiWebProvider
from providers.openai_api import OpenAiApiProvider


PROVIDERS = {
    "gemini-api": {
        "label": "Gemini API",
        "capabilities": ProviderCapabilities(
            ("translate", "polish", "pronouns", "review", "glossary", "characters"),
            batch=True, attachments=True, thinking=True, streaming=True,
        ),
    },
    "gemini-web": {
        "label": "Gemini Web",
        "capabilities": ProviderCapabilities(
            ("translate", "polish", "pronouns", "review", "glossary", "characters"), browser=True, batch=True, thinking=True,
        ),
    },
    "openai-api": {
        "label": "OpenAI API",
        "capabilities": ProviderCapabilities(
            ("translate", "polish", "pronouns", "review", "glossary", "characters"),
            attachments=True, thinking=True,
        ),
    },
    "chatgpt-web": {
        "label": "ChatGPT Web",
        "capabilities": ProviderCapabilities(
            ("translate", "polish", "pronouns", "review", "glossary", "characters"),
            browser=True, batch=True, attachments=True, thinking=True,
        ),
    },
}

PROVIDER_CLASSES = {
    "gemini-api": GeminiApiProvider,
    "gemini-web": GeminiWebProvider,
    "openai-api": OpenAiApiProvider,
    "chatgpt-web": ChatGptWebProvider,
}


def create_provider(provider_id, generate, stage):
    provider_id = str(provider_id or "").strip().lower()
    metadata = PROVIDERS.get(provider_id)
    if not metadata or stage not in metadata["capabilities"].stages:
        raise ValueError(f"{provider_id or 'Provider trống'} không hỗ trợ công đoạn {stage}")
    return PROVIDER_CLASSES[provider_id](generate)


def provider_payload():
    return [
        {
            "id": provider_id,
            "label": value["label"],
            "capabilities": {
                "stages": list(value["capabilities"].stages),
                "browser": value["capabilities"].browser,
                "batch": value["capabilities"].batch,
                "attachments": value["capabilities"].attachments,
                "thinking": value["capabilities"].thinking,
                "streaming": value["capabilities"].streaming,
            },
        }
        for provider_id, value in PROVIDERS.items()
    ]


def _stage_provider(config, stage, default):
    value = str(config.get(f"{stage}_provider", default)).strip().lower()
    if stage != "translate" and value == "off":
        return value
    provider = PROVIDERS.get(value)
    if not provider or stage not in provider["capabilities"].stages:
        raise ValueError(f"{value or 'Provider trống'} không hỗ trợ công đoạn {stage}")
    return value


def pipeline_config(config):
    """Resolve stage choices to a verified compatibility runner and legacy settings."""
    result = dict(config or {})
    stages = {
        "translate": _stage_provider(result, "translate", "gemini-api"),
        "polish": _stage_provider(result, "polish", "gemini-api"),
        "pronouns": _stage_provider(result, "pronouns", "gemini-api"),
        "review": _stage_provider(result, "review", "gemini-api"),
    }
    translate = stages["translate"]
    result["resolved_pipeline"] = "stage"
    result["stage_providers"] = stages
    models = {
        stage: str(result.get(f"{stage}_stage_model", "")).strip()
        for stage in stages
    }
    thinking = {
        stage: str(result.get(f"{stage}_stage_thinking", "")).strip()
        for stage in stages
    }
    if models["translate"]:
        key = {
            "gemini-api": "translate_model", "gemini-web": "gemini_web_model",
            "openai-api": "gpt_api_translate_model", "chatgpt-web": "chatgpt_model",
        }[translate]
        result[key] = models["translate"]
    if thinking["translate"]:
        key = {
            "gemini-api": "gemini_api_thinking", "gemini-web": "gemini_thinking",
            "openai-api": "gpt_api_translate_effort", "chatgpt-web": "chatgpt_thinking",
        }[translate]
        result[key] = thinking["translate"]
    return result
