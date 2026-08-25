import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.config import REVIEW_BG_CRITERIA
from cores.full_review import load_review_chapters, review_worker_count
from cores.full_review import service as review_service
from cores.full_review import runner as review_runner
from cores.postprocess import build_translation_review_prompt
from cores.full_review import build_review_prompt, prepare_review_item, process_review_result


class ReviewAllTests(unittest.TestCase):
    def test_review_json_accepts_web_control_character_and_removes_end_marker(self):
        response = '{"overall_score": 8.5, "issues": [], "gender_ok": true, "address_ok": true, "summary": "Dòng một\nDòng hai ###END###"}'
        result = review_service.parse_review_json(response)
        self.assertEqual(result["overall_score"], 8.5)
        self.assertEqual(result["summary"], "Dòng một\nDòng hai ")

    def test_review_json_rejects_incomplete_schema(self):
        with self.assertRaisesRegex(ValueError, "overall_score"):
            review_service.parse_review_json("{}")

    def test_web_review_uses_plain_json_without_end_marker_prompt(self):
        response = '{"overall_score": 9, "issues": [], "gender_ok": true, "address_ok": true, "summary": "Ổn"}'
        captured = []

        def transport(prompt, **_kwargs):
            captured.append(prompt)
            return response

        values = {"review_stage_model": "test", "review_stage_thinking": "cao"}
        with patch.dict(
            review_service.TRANSPORT_OVERRIDES,
            {"chatgpt-web": transport},
            clear=True,
        ), patch.object(
            review_service,
            "option",
            side_effect=lambda key, default=None: values.get(key, default),
        ):
            review_service.call_review_api("review prompt", "chatgpt-web")

        self.assertEqual("review prompt", captured[0])

    def test_review_json_ignores_surrounding_prose(self):
        response = 'Kết quả:\n{"overall_score": 9, "issues": [], "gender_ok": true, "address_ok": true, "summary": "Ổn"}\nHết.'
        self.assertEqual(9, review_service.parse_review_json(response)["overall_score"])

    def test_all_four_engines_can_review(self):
        response = '{"overall_score": 9, "issues": [], "gender_ok": true, "address_ok": true, "summary": "Ổn"}'
        document = {"name": "characters.md", "content": "## Alice"}
        for provider in ("gemini-api", "gemini-web", "openai-api", "chatgpt-web"):
            calls = []

            def transport(prompt, **kwargs):
                calls.append((prompt, kwargs))
                return response

            values = {
                "review_stage_model": "test-model",
                "review_stage_thinking": "high",
            }
            with (
                patch.dict(
                    review_service.TRANSPORT_OVERRIDES,
                    {provider: transport},
                    clear=True,
                ),
                patch.object(
                    review_service,
                    "option",
                    side_effect=lambda key, default=None: values.get(key, default),
                ),
            ):
                result = review_service.call_review_api("prompt", provider, (document,))

            self.assertEqual(result["overall_score"], 9)
            self.assertEqual(len(calls), 1)
            self.assertIn("Alice", str(calls[0]))

    def test_web_review_is_serial_but_api_review_can_be_parallel(self):
        self.assertEqual(review_worker_count("gemini-web", 10), 1)
        self.assertEqual(review_worker_count("chatgpt-web", 10), 1)
        self.assertEqual(review_worker_count("gemini-api", 10), 10)
        self.assertEqual(review_worker_count("openai-api", 10), 10)

    def test_next_batch_waits_for_current_batch_to_finish(self):
        items = [
            (f"v1_c{i}_s1", i, "Raw title", "Raw", "Title", "Translation")
            for i in range(1, 5)
        ]
        started = []
        first_batch_started = threading.Event()
        release_first_batch = threading.Event()

        def call_api(_prompt, _provider, _attachments=()):
            started.append(len(started) + 1)
            if len(started) >= 2:
                first_batch_started.set()
            release_first_batch.wait(2)
            return {
                "overall_score": 9,
                "issues": [],
                "gender_ok": True,
                "address_ok": True,
                "summary": "Ổn",
            }

        with tempfile.TemporaryDirectory() as directory, patch.object(
            review_runner, "call_review_api", side_effect=call_api
        ), patch.object(
            review_runner, "build_reference_documents", return_value=()
        ), patch.object(review_runner.time, "sleep"):
            root = Path(directory)
            thread = threading.Thread(
                target=review_runner.run_review_items,
                args=(items, "", {}, []),
                kwargs={
                    "provider": "gemini-api",
                    "batch_size": 2,
                    "workers": 4,
                    "sleep_between": 0,
                    "review_path": root / "review.json",
                    "manual_path": root / "manual_check.json",
                },
            )
            thread.start()
            try:
                self.assertTrue(first_batch_started.wait(1))
                threading.Event().wait(0.05)
                self.assertEqual(len(started), 2)
            finally:
                release_first_batch.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(started), 4)

    def test_medium_issue_is_added_to_manual_check(self):
        review_store = {}
        manual_list = []

        process_review_result(
            "v1_c1_s1",
            1,
            {
                "overall_score": 7,
                "issues": [{"severity": "trung bình"}],
                "gender_ok": True,
                "address_ok": True,
            },
            review_store,
            manual_list,
        )

        self.assertIn("v1_c1_s1", review_store)
        self.assertEqual(manual_list, ["v1_c1_s1"])

    def test_load_review_chapters_pairs_matching_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            translated_dir = root / "translated"
            raw_dir.mkdir()
            translated_dir.mkdir()
            (raw_dir / "v1_c1_s1.md").write_text(
                "# 原题\n![ảnh](raw.jpg)\n原文", encoding="utf-8"
            )
            (translated_dir / "v1_c1_s1.md").write_text(
                "# Tiêu đề\n![ảnh](translated.jpg)\nBản dịch", encoding="utf-8"
            )

            chapters, missing_raw = load_review_chapters(raw_dir, translated_dir)

        self.assertEqual(missing_raw, [])
        self.assertEqual(chapters[0]["raw_title"], "原题")
        self.assertEqual(chapters[0]["raw_content"], "原文")
        self.assertEqual(chapters[0]["title_translation"], "Tiêu đề")
        self.assertEqual(chapters[0]["translation"], "Bản dịch")

    def test_review_item_keeps_full_raw_and_translation(self):
        raw = "中" * 9000 + "RAW_END"
        translation = "bản dịch " * 2000 + "TRANSLATION_END"
        item = prepare_review_item({
            "id": "v1_c174_s1",
            "raw_title": "原题",
            "raw_content": raw,
            "title_translation": "Tiêu đề",
            "translation": translation,
        })
        self.assertEqual(item[3], raw)
        self.assertEqual(item[5], translation)
        self.assertTrue(item[3].endswith("RAW_END"))
        self.assertTrue(item[5].endswith("TRANSLATION_END"))

    def test_prompt_is_language_neutral_and_contains_both_ends(self):
        prompt = build_review_prompt("v1_c1_s1", 1, "原题", "开头 RAW_END", "Tiêu đề", "Mở đầu TRANSLATION_END")
        self.assertIn("ngôn ngữ nguồn bất kỳ sang tiếng Việt", prompt)
        self.assertIn("RAW_END", prompt)
        self.assertIn("TRANSLATION_END", prompt)
        self.assertNotIn("Hàn-Việt", prompt)
        self.assertNotIn("bản gốc tiếng Hàn", prompt)

    def test_review_all_uses_exact_background_review_prompt(self):
        arguments = ("v1_c2_s1", 2, "原题", "原文", "Tiêu đề", "Bản dịch", "glossary")
        self.assertEqual(
            build_review_prompt(*arguments),
            build_translation_review_prompt(*arguments, REVIEW_BG_CRITERIA),
        )


if __name__ == "__main__":
    unittest.main()
