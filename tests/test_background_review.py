import tempfile
import unittest
import importlib
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from pathlib import Path
from unittest.mock import Mock

from cores.translation import runner as translation_runner
from cores.postprocess import runtime as configured_runtime
from cores.postprocess import run_background_review
from cores.postprocess.runtime import TRANSPORT_OVERRIDES


runtime_module = importlib.import_module("cores.postprocess.runtime")


class BackgroundReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.review_path = str(Path(self.temporary.name) / "review.json")

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, responses, documents=()):
        remaining = iter(responses)

        def generate(_stage, _prompt, _attachments=()):
            result = next(remaining)
            if isinstance(result, Exception):
                raise result
            return result, "gemini-api", "review-model"

        with (
            patch(
                "cores.postprocess.review.build_reference_documents",
                return_value=documents,
            ) as build_documents,
            patch.object(configured_runtime, "REVIEW_JSON", self.review_path),
            patch.object(configured_runtime, "generate", side_effect=generate) as generate_mock,
            patch.object(configured_runtime, "provider", return_value="gemini-api"),
            patch.object(configured_runtime, "model_and_thinking", return_value=("review-model", "high")),
            patch.object(configured_runtime, "switch_api_key") as switch,
            patch.object(configured_runtime, "log_api_call"),
            patch("cores.postprocess.review.time.sleep"),
        ):
            run_background_review("v1_c1_s1", 1, "Tiêu đề", "Bản dịch")
        return generate_mock, switch, build_documents

    def test_review_sends_relevant_character_snapshot(self):
        document = {"name": "characters.md", "content": "## Alice"}
        generate, _switch, build_documents = self._run(
            ['{"overall_score": 10, "issues": [], "summary": "ổn"}'],
            (document,),
        )

        self.assertEqual(generate.call_args.args[2], (document,))
        self.assertIn("characters.md", generate.call_args.args[1])
        build_documents.assert_called_once()
        self.assertTrue(build_documents.call_args.kwargs["include_translation"])

    def test_4xx_switches_key_then_review_continues(self):
        generate, switch, _build = self._run([RuntimeError("403 PERMISSION_DENIED"), '{"overall_score": 9, "issues": [], "summary": "Ổn"}'])
        self.assertEqual(generate.call_count, 2)
        switch.assert_called_once_with()
        self.assertTrue(Path(self.review_path).is_file())

    def test_5xx_retries_same_key(self):
        generate, switch, _build = self._run([RuntimeError("503 unavailable"), '{"overall_score": 8, "issues": [], "summary": "Ổn"}'])
        self.assertEqual(generate.call_count, 2)
        switch.assert_not_called()

    def test_success_emits_review_saved_web_event(self):
        output = StringIO()
        with patch.dict("os.environ", {"NOVEL_WEB_MODE": "1"}), redirect_stdout(output):
            self._run(['{"overall_score": 10, "issues": [], "summary": "ổn"}'])
        self.assertIn('"type":"review_saved"', output.getvalue())
        self.assertIn('"chapter":"v1_c1_s1"', output.getvalue())

    def test_custom_criteria_and_language_neutral_role_are_in_prompt(self):
        with patch.object(configured_runtime, "REVIEW_BG_CRITERIA", "TIÊU CHÍ RIÊNG CỦA USER"):
            generate, _switch, _build = self._run(['{"overall_score": 10, "issues": [], "summary": "Ổn"}'])
        prompt = generate.call_args.args[1]
        self.assertIn("ngôn ngữ nguồn bất kỳ sang tiếng Việt", prompt)
        self.assertIn("TIÊU CHÍ RIÊNG CỦA USER", prompt)
        self.assertNotIn("Hàn-Việt", prompt)
        self.assertNotIn("tiếng Hàn", prompt)

    def test_postprocess_runtime_routes_all_four_review_engines(self):
        response = '{"overall_score": 9, "issues": [], "summary": "Ổn"}'
        for provider in ("gemini-api", "gemini-web", "openai-api", "chatgpt-web"):
            transport = Mock(return_value=response)
            values = {
                "review_provider": provider,
                "review_stage_model": "review-only",
                "review_stage_thinking": "high",
            }
            with (
                patch.object(runtime_module, "option", side_effect=lambda key, default=None: values.get(key, default)),
                patch.dict(TRANSPORT_OVERRIDES, {provider: transport}, clear=True),
            ):
                text, selected, model = configured_runtime.generate("review", "prompt")
            self.assertEqual((text, selected, model), (response, provider, "review-only"))
            transport.assert_called_once()

    def test_single_translation_saves_final_text_before_queueing_review(self):
        events = []
        chapter = {"id": "v1_c1_s1", "title": "Gốc", "content": "Raw"}

        def save(_path, _directory, title, content, *, image_markers=None):
            events.append(("save", title, content))
            return "translated/v1_c1_s1.md"

        def enqueue(item, _number, _context):
            events.append(("review", item["title_translation"], item["translation"]))

        with (
            patch.object(translation_runner, "scan_md_dir", return_value=["raw/v1_c1_s1.md"]),
            patch.object(translation_runner, "is_translated", return_value=False),
            patch.object(translation_runner, "load_md_chapter", return_value=chapter),
            patch.object(translation_runner, "filtered_context_and_names", return_value=("context", [], "pronouns.json")),
            patch.object(translation_runner, "format_pronoun_context", return_value="pronouns"),
            patch.object(translation_runner, "_export_recent_translations"),
            patch.object(translation_runner, "option", return_value=0),
            patch.object(translation_runner, "bool_option", return_value=False),
            patch.object(translation_runner, "save_translated_md", side_effect=save),
            patch.object(translation_runner, "enqueue_background_review", side_effect=enqueue),
        ):
            result = translation_runner.run_single_translation(
                lambda *_args: ("Bản dịch", "Nội dung dịch"),
                "raw",
                "translated",
                "context.yaml",
                postprocess=lambda *_args: ("Đã hiệu đính", "Nội dung cuối"),
            )

        self.assertEqual(result, 1)
        self.assertEqual(events, [("save", "Đã hiệu đính", "Nội dung cuối"), ("review", "Đã hiệu đính", "Nội dung cuối")])


if __name__ == "__main__":
    unittest.main()
