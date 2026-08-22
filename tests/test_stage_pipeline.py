import json
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cores.translation import stage as translation_stage
from cores.postprocess import run_background_review, runtime as configured_runtime


runtime_module = importlib.import_module("cores.postprocess.runtime")
polish_module = importlib.import_module("cores.postprocess.polish")


CHAPTER = {
    "id": "v1_c1_s1",
    "title": "Raw title",
    "content": "Raw content",
    "title_translation": "Tiêu đề",
    "translation": "Nội dung",
}


class StagePipelineTests(unittest.TestCase):
    def test_stage_model_and_thinking_are_independent(self):
        values = {
            "translate_stage_model": "translate-only",
            "translate_stage_thinking": "medium",
            "polish_stage_model": "polish-only",
            "polish_stage_thinking": "high",
        }
        with patch.object(
            translation_stage,
            "option",
            side_effect=lambda key, default=None: values.get(key, default),
        ):
            self.assertEqual(
                translation_stage.model_and_thinking("translate", "openai-api"),
                ("translate-only", "medium"),
            )
            self.assertEqual(
                translation_stage.model_and_thinking("polish", "openai-api"),
                ("polish-only", "high"),
            )

    def test_gemini_web_polish_uses_web_generator(self):
        response = "###TITLE###\nMới\n###CONTENT###\nBản mới\n###END###"
        generate = Mock(return_value=response)
        values = {"polish_provider": "gemini-web", "gemini_web_model": "pro", "gemini_thinking": "extended"}
        with patch.object(runtime_module, "option", side_effect=lambda key, default=None: values.get(key, default)), patch.dict(
            translation_stage.TRANSPORT_OVERRIDES, {"gemini-web": generate}, clear=True
        ), patch.object(configured_runtime, "log_api_call"), patch.object(
            polish_module, "build_characters_snapshot", return_value=None
        ), patch.object(polish_module, "build_pronouns_snapshot", return_value=None):
            result = configured_runtime.polish_translation(
                dict(CHAPTER), 1, "context", "pronouns", pronouns_file=None
            )
        self.assertEqual(result, ("Mới", "Bản mới"))
        self.assertEqual(generate.call_args.kwargs["web_model"], "pro")

    def test_openai_review_saves_existing_review_shape(self):
        response = json.dumps({"overall_score": 9, "issues": [], "summary": "Ổn"}, ensure_ascii=False)
        call = Mock(return_value=response)
        values = {
            "review_provider": "openai-api",
            "gpt_api_review_model": "review-model",
            "gpt_api_review_effort": "high",
        }
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            configured_runtime, "REVIEW_JSON", str(Path(temporary) / "review.json")
        ), patch.object(runtime_module, "option", side_effect=lambda key, default=None: values.get(key, default)), patch.dict(
            translation_stage.TRANSPORT_OVERRIDES, {"openai-api": call}, clear=True
        ), patch.object(configured_runtime, "log_api_call"):
            run_background_review(
                "v1_c1_s1", 1, "Tiêu đề", "Nội dung", "context", "Raw content",
                raw_title="Raw title",
            )
            saved = json.loads(Path(configured_runtime.REVIEW_JSON).read_text(encoding="utf-8"))
        self.assertEqual(saved["v1_c1_s1"]["score"], 9)
        self.assertEqual(call.call_args.kwargs["reasoning_effort"], "high")

    def test_chatgpt_web_polish_uses_chatgpt_stage_settings(self):
        response = "###TITLE###\nMới\n###CONTENT###\nBản mới\n###END###"
        generate = Mock(return_value=response)
        values = {
            "polish_provider": "chatgpt-web",
            "polish_stage_model": "gpt-polish",
            "polish_stage_thinking": "cao",
        }
        with patch.object(
            runtime_module,
            "option",
            side_effect=lambda key, default=None: values.get(key, default),
        ), patch.dict(
            translation_stage.TRANSPORT_OVERRIDES, {"chatgpt-web": generate}, clear=True
        ), patch.object(configured_runtime, "log_api_call"), patch.object(
            polish_module, "build_characters_snapshot", return_value=None
        ), patch.object(polish_module, "build_pronouns_snapshot", return_value=None):
            result = configured_runtime.polish_translation(
                dict(CHAPTER), 1, "context", "pronouns", pronouns_file=None
            )
        self.assertEqual(result, ("Mới", "Bản mới"))
        self.assertEqual(generate.call_args.kwargs["chatgpt_model"], "gpt-polish")
        self.assertEqual(generate.call_args.kwargs["chatgpt_thinking"], "cao")

    def test_chatgpt_web_pronouns_use_pronoun_stage_settings(self):
        generate = Mock(return_value="pronoun result")
        values = {
            "pronouns_provider": "chatgpt-web",
            "pronouns_stage_model": "gpt-pronouns",
            "pronouns_stage_thinking": "vừa",
        }

        def update(*args, **kwargs):
            self.assertEqual(kwargs["model"], "gpt-pronouns")
            self.assertEqual(kwargs["generate"]("prompt"), "pronoun result")

        with patch.object(
            runtime_module,
            "option",
            side_effect=lambda key, default=None: values.get(key, default),
        ), patch.dict(
            translation_stage.TRANSPORT_OVERRIDES, {"chatgpt-web": generate}, clear=True
        ), patch.object(runtime_module, "_update_pronoun_memory", side_effect=update):
            configured_runtime.update_pronoun_memory(
                "v1_c1_s1", 1, "Nội dung", "pronouns.json"
            )
        self.assertEqual(generate.call_args.kwargs["chatgpt_model"], "gpt-pronouns")
        self.assertEqual(generate.call_args.kwargs["chatgpt_thinking"], "vừa")


if __name__ == "__main__":
    unittest.main()
