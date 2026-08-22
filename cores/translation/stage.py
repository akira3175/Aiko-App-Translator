"""Translate one chapter through the selected provider."""

from cores.api_logging import log_project_api_call as log_api_call
from cores.config import NOVEL_TXT
from cores.r19 import (
    mask_contexts,
    prepare_chapters,
    restore_results,
    strip_previous_context,
    translate_fragments,
)
from cores.config.runtime import option
from cores.stages import (
    TRANSPORT_OVERRIDES,
    build_reference_documents,
    generate_stage,
    parse_title_content,
    stage_model_and_thinking,
    stage_provider,
)
from cores.translation.prompts import build_single_prompt, with_character_document_instruction


def provider(stage):
    return stage_provider(stage, get_option=option)


def model_and_thinking(stage, provider_id):
    return stage_model_and_thinking(stage, provider_id, get_option=option)


def generate(stage, prompt, attachments=()):
    provider_id = provider(stage)
    model, _thinking = model_and_thinking(stage, provider_id)
    response, _provider_id, _model = generate_stage(
        stage,
        prompt,
        provider=provider_id,
        get_option=option,
        overrides=TRANSPORT_OVERRIDES,
        attachments=attachments,
    )
    return response, model


def translate_r19_fragments(entries):
    provider_id = provider("translate")
    model, _thinking = model_and_thinking("translate", provider_id)

    def generate_fragment(prompt):
        return generate_stage(
            "translate",
            prompt,
            provider=provider_id,
            get_option=option,
            overrides=TRANSPORT_OVERRIDES,
        )[0].text

    switcher = None
    key_count = 1
    if provider_id == "gemini-api":
        from cores.gemini import API_KEYS, switch_api_key

        switcher = switch_api_key
        key_count = max(1, len(API_KEYS))
    return translate_fragments(
        entries,
        generate_fragment,
        provider=provider_id,
        model=model,
        switcher=switcher,
        key_count=key_count,
    )


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    masked_chapters, r19_entries = prepare_chapters([chapter])
    masked_context, masked_pronouns = mask_contexts(
        [context_text, pronoun_context], r19_entries
    )
    previous = ""
    try:
        with open(NOVEL_TXT, "r", encoding="utf-8") as file:
            previous = file.read().strip()
    except OSError:
        pass
    prompt = build_single_prompt(
        masked_chapters[0],
        masked_context,
        masked_pronouns,
        strip_previous_context(previous),
    )
    provider_id = provider("translate")
    documents = build_reference_documents(chapter, pronoun_context)
    if any(item["name"] == "characters.md" for item in documents):
        prompt = with_character_document_instruction(prompt)
    response, model = generate("translate", prompt, documents)
    log_api_call(
        chapter["id"],
        "translate",
        f"{provider_id}:{model}",
        prompt,
        response.text,
        attachments=list(documents),
    )
    result = parse_title_content(response.text, "Dịch")
    if r19_entries:
        result = restore_results(
            [result], r19_entries, translate_r19_fragments(r19_entries)
        )[0]
    return result
