import tempfile
import unittest
from pathlib import Path

from cores.r19 import storage as r19_storage
from services import ai_logs
from services.r19 import repository
from services.r19.service import R19Service


class R19ServiceTests(unittest.TestCase):
    def _service(self, root, project):
        return R19Service(
            safe_project=lambda _name: project,
            words_path=root / "data" / "r19_words.txt",
            config_path=root / ".runtime" / "r19.json",
            default_words_path=root / "defaults" / "r19_words.txt",
            default_model="default-model",
            default_context_chapters=0,
            default_prompt_prefix="Default prompt",
            active_translation=lambda: None,
            translation_guard=object(),
            generate=lambda _prompt, _model: "",
            log_call=lambda *_args: None,
        )

    def test_service_round_trip_and_task_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            defaults = root / "defaults" / "r19_words.txt"
            defaults.parent.mkdir()
            defaults.write_text("默认词 = từ mặc định\n", encoding="utf-8")
            service = self._service(root, project)

            saved = service.save(
                "project",
                {
                    "enabled": True,
                    "words": "敏感词 = từ nhạy cảm\n",
                    "model": "test-model",
                    "context_chapters": 4,
                    "prompt_prefix": "Prompt R19",
                },
            )

            self.assertTrue(saved["enabled"])
            self.assertTrue(service.project_enabled("project"))
            self.assertEqual(
                4, service.task_options("project")["previous_context_chapters"]
            )

    def test_repository_round_trip_and_pipeline_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            words = root / "data" / "r19_words.txt"
            config = root / ".runtime" / "r19.json"
            defaults = root / "defaults" / "r19_words.txt"
            defaults.parent.mkdir()
            defaults.write_text("默认词 = từ mặc định\n", encoding="utf-8")

            repository.save(
                project,
                {
                    "enabled": True,
                    "words": "敏感词 = từ nhạy cảm\n",
                    "model": "test-model",
                    "context_chapters": 3,
                    "prompt_prefix": "Prompt R19",
                },
                words,
                config,
                "default-model",
                0,
                "Default prompt",
            )
            data = repository.payload(
                project,
                words,
                config,
                defaults,
                "default-model",
                0,
                "Default prompt",
            )

        self.assertTrue(data["enabled"])
        self.assertEqual("test-model", data["model"])
        self.assertEqual(1, data["count"])
        self.assertEqual(3, repository.task_options(data)["previous_context_chapters"])

    def test_ai_log_service_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            ai_logs.append_r19(
                project,
                "term",
                "model",
                "Authorization: Bearer private-token",
                "sk-abcdefghijklmnopqrstuvwxyz",
                True,
            )
            item = ai_logs.read(project)["items"][0]

        self.assertNotIn("private-token", item["prompt"])
        self.assertEqual("[REDACTED]", item["response"])

    def test_storage_paths_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("甲\n", encoding="utf-8")
            second.write_text("乙\n", encoding="utf-8")

            r19_storage.save_word_translation("甲", "một", first)

            first_terms, first_translations = r19_storage.load_word_mappings(first)
            second_terms, second_translations = r19_storage.load_word_mappings(second)

        self.assertEqual(["甲"], first_terms)
        self.assertEqual("một", first_translations["甲"])
        self.assertEqual(["乙"], second_terms)
        self.assertEqual({}, second_translations)


if __name__ == "__main__":
    unittest.main()
