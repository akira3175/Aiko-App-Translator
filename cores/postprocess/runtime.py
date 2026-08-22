"""Configured dependencies for the legacy-compatible post-processing flow."""

import atexit
import threading

from cores.api_logging import log_project_api_call
from cores.chapters.files import has_foreign
from cores.config import (
    CHARACTERS_MD,
    FIX_MAX_RETRY,
    MANUAL_CHECK_JSON,
    REVIEW_BG_CRITERIA,
    REVIEW_JSON,
)
from cores.gemini import switch_api_key
from cores.postprocess.language_check import fix_translation as _fix_translation
from cores.postprocess.pipeline import run_post_translation_pipeline as _run_pipeline
from cores.postprocess.polish import polish_translation as _polish_translation
from cores.postprocess.review import (
    enqueue_background_review as _enqueue_review,
    run_background_review as _run_review,
)
from cores.pronouns import update_pronoun_memory as _update_pronoun_memory
from cores.config.runtime import int_option, option
from cores.stages.runtime import (
    TRANSPORT_OVERRIDES,
    browser_lifecycle,
    generate_stage,
    stage_model_and_thinking,
    stage_provider,
)
from cores.translation.prompts import (
    _r19_placeholder_instruction,
    project_polish_prompt,
    with_character_document_instruction,
    wrap_r19_prompt,
)


class PostprocessRuntime:
    def __init__(self):
        self.REVIEW_BG_CRITERIA = REVIEW_BG_CRITERIA
        self.REVIEW_JSON = REVIEW_JSON
        self.MANUAL_CHECK_JSON = MANUAL_CHECK_JSON
        self.FIX_MAX_RETRY = FIX_MAX_RETRY
        self._review_lock = threading.Lock()
        self._latest_review_tokens = {}
        self._review_executor = None
        self._opened_browser_providers = set()
        atexit.register(self.close_browsers)

    switch_api_key = staticmethod(switch_api_key)
    log_api_call = staticmethod(log_project_api_call)
    has_foreign = staticmethod(has_foreign)
    int_option = staticmethod(int_option)
    wrap_r19_prompt = staticmethod(wrap_r19_prompt)
    _r19_placeholder_instruction = staticmethod(_r19_placeholder_instruction)
    project_polish_prompt = staticmethod(project_polish_prompt)
    with_character_document_instruction = staticmethod(with_character_document_instruction)

    def provider(self, stage):
        return stage_provider(stage, get_option=option)

    def model_and_thinking(self, stage):
        provider = self.provider(stage)
        if provider == "off":
            return "", ""
        return stage_model_and_thinking(stage, provider, get_option=option)

    def enabled(self, stage):
        provider = self.provider(stage)
        if provider == "off":
            return False
        model, _thinking = self.model_and_thinking(stage)
        return model.strip().lower() not in {"", "none"}

    def generate(self, stage, prompt, attachments=()):
        provider = self.provider(stage)
        self.setup_browser(provider)
        response, provider, model = generate_stage(
            stage,
            prompt,
            provider=self.provider(stage),
            get_option=option,
            overrides=TRANSPORT_OVERRIDES,
            attachments=attachments,
        )
        return response.text.strip(), provider, model

    def setup_browser(self, provider):
        if provider in TRANSPORT_OVERRIDES or provider in self._opened_browser_providers:
            return
        setup, _close = browser_lifecycle(provider)
        if setup:
            setup()
            self._opened_browser_providers.add(provider)

    def close_browsers(self):
        for provider in tuple(self._opened_browser_providers):
            _setup, close = browser_lifecycle(provider)
            if close:
                close()
        self._opened_browser_providers.clear()

    def switch_key_for(self, stage):
        if self.provider(stage) == "gemini-api":
            self.switch_api_key()

    def polish_translation(
        self, chapter, chapter_number, context_text="", pronoun_context="",
        characters_md_path=CHARACTERS_MD, pronouns_file=None, model=None,
        thinking_level=None,
    ):
        return _polish_translation(
            self, chapter, chapter_number, context_text, pronoun_context,
            characters_md_path, pronouns_file, model, thinking_level,
        )

    def fix_translation(
        self, chapter, chapter_number, context_text="", pronoun_context="",
        model=None, thinking_level=None,
    ):
        return _fix_translation(
            self, chapter, chapter_number, context_text, pronoun_context,
            model, thinking_level,
        )

    def update_pronoun_memory(
        self, chapter_id, chapter_number, translation_text, pronouns_file
    ):
        model, _thinking = self.model_and_thinking("pronouns")
        return _update_pronoun_memory(
            chapter_id,
            chapter_number,
            translation_text,
            pronouns_file=pronouns_file,
            model=model,
            generate=lambda prompt: self.generate("pronouns", prompt)[0],
            switch_key=lambda: self.switch_key_for("pronouns"),
        )


runtime = PostprocessRuntime()


def run_post_translation_pipeline(
    chapter, chapter_number, context_text, pronoun_context, pronouns_file
):
    return _run_pipeline(
        runtime, chapter, chapter_number, context_text, pronoun_context, pronouns_file
    )


def enqueue_background_review(chapter, chapter_number, context_text=""):
    return _enqueue_review(runtime, chapter, chapter_number, context_text)


def run_background_review(*args, **kwargs):
    return _run_review(runtime, *args, **kwargs)
