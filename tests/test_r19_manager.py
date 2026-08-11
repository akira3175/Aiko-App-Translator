import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from cores import r19_translation


class R19ManagerTests(unittest.TestCase):
    def test_global_words_and_enabled_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            with (
                patch.object(app, "R19_WORDS_FILE", root / "r19_words.txt"),
                patch.object(app, "R19_CONFIG_FILE", root / ".runtime" / "r19.json"),
                patch.object(app, "safe_project", lambda _name: project),
            ):
                saved = app.write_r19("project", {
                    "enabled": True,
                    "words": "# note\n민감한 표현\n敏感词\n",
                    "model": "gemini-test",
                    "context_chapters": 5,
                    "prompt_prefix": 'Prompt riêng """',
                })
                self.assertTrue(saved["enabled"])
                self.assertEqual(saved["count"], 2)
                self.assertEqual(saved["model"], "gemini-test")
                self.assertEqual(saved["context_chapters"], 5)
                self.assertEqual(saved["prompt_prefix"], 'Prompt riêng """')
                self.assertEqual(saved["defaults"]["model"], "gemini-3.5-flash-lite")
                self.assertEqual(saved["defaults"]["context_chapters"], 0)
                self.assertEqual(app.r19_payload("project"), saved)
                self.assertNotIn("enabled", json.loads((root / ".runtime" / "r19.json").read_text(encoding="utf-8")))

    def test_r19_task_options_only_override_context_when_enabled(self):
        with patch.object(
            app,
            "r19_payload",
            return_value={
                "enabled": True,
                "model": "r19-model",
                "context_chapters": 7,
                "prompt_prefix": 'Prefix """',
            },
        ):
            enabled = app.r19_task_options("project-a")
        self.assertEqual(enabled["previous_context_chapters"], 7)
        with patch.object(
            app,
            "r19_payload",
            return_value={
                "enabled": False,
                "model": "r19-model",
                "context_chapters": 7,
                "prompt_prefix": 'Prefix """',
            },
        ):
            disabled = app.r19_task_options("project-b")
        self.assertNotIn("previous_context_chapters", disabled)

    def test_r19_model_is_hidden_from_general_settings(self):
        keys = {item["key"] for item in app.settings_payload()["items"]}
        self.assertNotIn("r19_model", keys)

    def test_background_review_criteria_is_an_editable_textarea(self):
        item = next(item for item in app.settings_payload()["items"] if item["key"] == "review_bg_criteria")
        self.assertEqual(item["type"], "textarea")
        self.assertEqual(item["group"], "general")
        self.assertIn("Thiếu nội dung", item["value"])

    def test_cannot_enable_empty_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(app, "R19_WORDS_FILE", root / "r19_words.txt"),
                patch.object(app, "R19_CONFIG_FILE", root / ".runtime" / "r19.json"),
            ):
                with self.assertRaisesRegex(ValueError, "ít nhất một cụm"):
                    app.write_r19("project", {"enabled": True, "words": "# only a note\n"})

    def test_enabled_state_is_separate_for_each_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects = {name: root / name for name in ("a", "b")}
            for path in projects.values():
                path.mkdir()
            with (
                patch.object(app, "R19_WORDS_FILE", root / "r19_words.txt"),
                patch.object(app, "R19_CONFIG_FILE", root / ".runtime" / "r19.json"),
                patch.object(app, "safe_project", lambda name: projects[name]),
            ):
                app.write_r19("a", {"enabled": True, "words": "敏感词 = từ nhạy cảm\n"})
                self.assertTrue(app.r19_payload("a")["enabled"])
                self.assertFalse(app.r19_payload("b")["enabled"])

    def test_missing_word_file_uses_packaged_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default_words = root / "defaults" / "r19_words.txt"
            default_words.parent.mkdir()
            default_words.write_text("默认词 = từ mặc định\n", encoding="utf-8")
            with (
                patch.object(app, "R19_WORDS_FILE", root / "r19_words.txt"),
                patch.object(app, "R19_DEFAULT_WORDS_FILE", default_words),
                patch.object(app, "R19_CONFIG_FILE", root / ".runtime" / "r19.json"),
            ):
                payload = app.r19_payload()
        self.assertEqual(payload["words"], "默认词 = từ mặc định\n")
        self.assertEqual(payload["defaults"]["words"], payload["words"])

    def test_translate_word_from_manager_updates_same_file_and_writes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            words = root / "r19_words.txt"
            config = root / ".runtime" / "r19.json"
            project = root / "project"
            project.mkdir()
            words.write_text("敏感词\n", encoding="utf-8")
            with (
                patch.object(app, "R19_WORDS_FILE", words),
                patch.object(app, "R19_CONFIG_FILE", config),
                patch.object(app, "safe_project", lambda _name: project),
                patch.object(app, "active_translation", lambda: None),
                patch.object(app, "saved_settings", lambda: {"r19_model": "test-model"}),
                patch.object(app, "_call_r19_gemini", lambda _prompt, _model: '{"translation":"từ nhạy cảm"}'),
                patch.object(r19_translation, "R19_WORDS_FILE", words),
            ):
                result = app.translate_r19_word("project", {"source": "敏感词"})
            self.assertEqual(result["translation"], "từ nhạy cảm")
            self.assertIn("敏感词 = từ nhạy cảm", words.read_text(encoding="utf-8"))
            logs = list((project / "logs").glob("*.jsonl"))
            self.assertEqual(len(logs), 1)
            self.assertIn('"step": "r19_word"', logs[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
