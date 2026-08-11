import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores import dich_utils
from cores import translation_workflows


class BackgroundReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.review_path = str(Path(self.temporary.name) / "review.yaml")

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, responses):
        with (
            patch.object(dich_utils, "REVIEW_YAML", self.review_path),
            patch.object(dich_utils, "call_gemini", side_effect=responses) as generate,
            patch.object(dich_utils, "switch_api_key") as switch,
            patch.object(dich_utils, "log_api_call"),
            patch.object(dich_utils.time, "sleep"),
        ):
            dich_utils._run_background_review("v1_c1_s1", 1, "Tiêu đề", "Bản dịch")
        return generate, switch

    def test_4xx_switches_key_then_review_continues(self):
        generate, switch = self._run([RuntimeError("403 PERMISSION_DENIED"), '{"overall_score": 9, "issues": [], "summary": "Ổn"}'])
        self.assertEqual(generate.call_count, 2)
        switch.assert_called_once_with()
        self.assertTrue(Path(self.review_path).is_file())

    def test_5xx_retries_same_key(self):
        generate, switch = self._run([RuntimeError("503 unavailable"), '{"overall_score": 8, "issues": [], "summary": "Ổn"}'])
        self.assertEqual(generate.call_count, 2)
        switch.assert_not_called()

    def test_custom_criteria_and_language_neutral_role_are_in_prompt(self):
        with patch.object(dich_utils, "REVIEW_BG_CRITERIA", "TIÊU CHÍ RIÊNG CỦA USER"):
            generate, _switch = self._run(['{"overall_score": 10, "issues": [], "summary": "Ổn"}'])
        prompt = generate.call_args.args[0]
        self.assertIn("ngôn ngữ nguồn bất kỳ sang tiếng Việt", prompt)
        self.assertIn("TIÊU CHÍ RIÊNG CỦA USER", prompt)
        self.assertNotIn("Hàn-Việt", prompt)
        self.assertNotIn("tiếng Hàn", prompt)

    def test_single_translation_saves_final_text_before_queueing_review(self):
        events = []
        chapter = {"id": "v1_c1_s1", "title": "Gốc", "content": "Raw"}

        def save(_path, _directory, title, content):
            events.append(("save", title, content))
            return "translated/v1_c1_s1.md"

        def enqueue(item, _number, _context):
            events.append(("review", item["title_translation"], item["translation"]))

        with (
            patch.object(translation_workflows, "scan_md_dir", return_value=["raw/v1_c1_s1.md"]),
            patch.object(translation_workflows, "is_translated", return_value=False),
            patch.object(translation_workflows, "load_md_chapter", return_value=chapter),
            patch.object(translation_workflows, "_filtered_context_and_names", return_value=("context", [], "pronouns.yaml")),
            patch.object(translation_workflows, "format_pronoun_context", return_value="pronouns"),
            patch.object(translation_workflows, "export_recent_translations_to_txt_md"),
            patch.object(translation_workflows, "option", return_value=0),
            patch.object(translation_workflows, "bool_option", return_value=False),
            patch.object(translation_workflows, "save_translated_md", side_effect=save),
            patch.object(translation_workflows, "enqueue_background_review", side_effect=enqueue),
        ):
            result = translation_workflows.run_single_translation(
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
