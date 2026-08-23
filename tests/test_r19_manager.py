import json
import tempfile
import threading
import unittest
from pathlib import Path
from services.ai_logs import append_r19
from services.r19.service import R19Service
from services.settings_schema import (
    DEFAULT_REVIEW_BG_CRITERIA,
    HIDDEN_SETTINGS,
    SETTING_META,
)


class R19ManagerTests(unittest.TestCase):
    @staticmethod
    def service(root, projects, generate=lambda _prompt, _model: ""):
        return R19Service(
            safe_project=lambda name: projects[name],
            words_path=root / "r19_words.txt",
            config_path=root / ".runtime" / "r19.json",
            default_words_path=root / "defaults" / "r19_words.txt",
            default_model="gemini-3.5-flash-lite",
            default_context_chapters=0,
            default_prompt_prefix='Cách để AI dịch được prompt sau """',
            active_translation=lambda: None,
            translation_guard=threading.RLock(),
            generate=generate,
            log_call=append_r19,
        )

    def test_global_words_and_enabled_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            service = self.service(root, {"project": project})

            saved = service.save(
                "project",
                {
                    "enabled": True,
                    "words": "# note\n敏感한 표현\n敏感词\n",
                    "model": "gemini-test",
                    "context_chapters": 5,
                    "prompt_prefix": 'Prompt riêng """',
                },
            )

            self.assertTrue(saved["enabled"])
            self.assertEqual(2, saved["count"])
            self.assertEqual("gemini-test", saved["model"])
            self.assertEqual(5, saved["context_chapters"])
            self.assertEqual(saved, service.payload("project"))
            config = json.loads(
                (root / ".runtime" / "r19.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("enabled", config)

    def test_task_options_only_override_context_when_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            service = self.service(root, {"project": project})
            service.save(
                "project",
                {
                    "enabled": True,
                    "words": "敏感词",
                    "context_chapters": 7,
                },
            )
            self.assertEqual(
                7, service.task_options("project")["previous_context_chapters"]
            )
            service.save("project", {"enabled": False, "words": "敏感词"})
            self.assertNotIn(
                "previous_context_chapters", service.task_options("project")
            )

    def test_r19_and_background_review_schema(self):
        self.assertIn("r19_model", HIDDEN_SETTINGS)
        self.assertEqual("textarea", SETTING_META["review_bg_criteria"]["type"])
        self.assertEqual("general", SETTING_META["review_bg_criteria"]["group"])
        self.assertIn("Thiếu nội dung", DEFAULT_REVIEW_BG_CRITERIA)

    def test_cannot_enable_empty_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            service = self.service(root, {"project": project})
            with self.assertRaisesRegex(ValueError, "ít nhất một cụm"):
                service.save(
                    "project", {"enabled": True, "words": "# only a note\n"}
                )

    def test_enabled_state_is_separate_for_each_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects = {name: root / name for name in ("a", "b")}
            for path in projects.values():
                path.mkdir()
            service = self.service(root, projects)
            service.save("a", {"enabled": True, "words": "敏感词 = từ nhạy cảm\n"})
            self.assertTrue(service.payload("a")["enabled"])
            self.assertFalse(service.payload("b")["enabled"])

    def test_missing_word_file_uses_packaged_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default_words = root / "defaults" / "r19_words.txt"
            default_words.parent.mkdir()
            default_words.write_text("默认词 = từ mặc định\n", encoding="utf-8")
            service = self.service(root, {})
            payload = service.payload()
            self.assertEqual("默认词 = từ mặc định\n", payload["words"])
            self.assertEqual(payload["words"], payload["defaults"]["words"])

    def test_translate_word_updates_file_and_writes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            service = self.service(
                root,
                {"project": project},
                generate=lambda _prompt, _model: '{"translation":"từ nhạy cảm"}',
            )
            (root / "r19_words.txt").write_text("敏感词\n", encoding="utf-8")

            result = service.translate_word("project", {"source": "敏感词"})

            self.assertEqual("từ nhạy cảm", result["translation"])
            words = (root / "r19_words.txt").read_text(encoding="utf-8")
            self.assertIn("敏感词 = từ nhạy cảm", words)
            logs = list((project / "logs").glob("*.jsonl"))
            self.assertEqual(1, len(logs))
            self.assertIn('"step": "r19_word"', logs[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
