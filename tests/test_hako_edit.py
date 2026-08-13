import json
import os
import unittest
from unittest.mock import patch

import app


class _Response:
    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content.encode("utf-8")


class HakoEditTests(unittest.TestCase):
    def test_public_chapter_scan_deduplicates_ids_and_reads_titles(self):
        source = """
        <a href="/truyen/1-demo/c123-chuong-mot"><span>Chương 1: Mở đầu</span></a>
        <a href="/truyen/1-demo/c123-chuong-mot">Chương 1: Mở đầu</a>
        <a href="https://docln.sbs/truyen/1-demo/c456-chuong-hai">Chương 2 &amp; tiếp</a>
        """
        with patch.object(app, "urlopen", return_value=_Response(source)):
            result = app.hako_public_chapters("https://docln.sbs/truyen/1-demo")
        self.assertEqual([item["chapter_id"] for item in result["items"]], ["123", "456"])
        self.assertEqual(result["items"][1]["title"], "Chương 2 & tiếp")

    def test_public_chapter_scan_rejects_non_hako_and_chapter_urls(self):
        for value in ("https://example.com/truyen/1-demo", "https://docln.sbs/action/chapter/1/edit"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.hako_public_chapters(value)

    def test_edit_target_validation_rejects_duplicate_remote_ids(self):
        config = {
            "hako_edit_targets": [
                {"local_name": "v1_c1_s1.md", "chapter_id": "12", "remote_title": "Một"},
                {"local_name": "v1_c2_s1.md", "chapter_id": "12", "remote_title": "Hai"},
            ]
        }
        with patch.dict(os.environ, {"NOVEL_WEB_MODE": "1", "NOVEL_WEB_CONFIG": json.dumps(config)}):
            from cores import runtime_config
            from up import edit_hako

            runtime_config.task_config.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "bị chọn trùng"):
                edit_hako.edit_targets()
            runtime_config.task_config.cache_clear()

    def test_backend_accepts_and_normalizes_hako_edit_targets(self):
        result = app.validate_hako_edit_targets(
            [{"local_name": " v1_c2_s1.md ", "chapter_id": 123, "remote_title": " Chương 2 "}]
        )
        self.assertEqual(
            result,
            [{"local_name": "v1_c2_s1.md", "chapter_id": "123", "remote_title": "Chương 2"}],
        )

    def test_backend_rejects_duplicate_hako_edit_targets(self):
        with self.assertRaisesRegex(ValueError, "bị chọn trùng"):
            app.validate_hako_edit_targets(
                [
                    {"local_name": "v1_c1_s1.md", "chapter_id": "12", "remote_title": "Một"},
                    {"local_name": "v1_c2_s1.md", "chapter_id": "12", "remote_title": "Hai"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
