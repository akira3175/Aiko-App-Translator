import json
import tempfile
import unittest
from pathlib import Path

from services.context import ContextService


class ContextServiceTests(unittest.TestCase):
    def _service(self, project):
        return ContextService(lambda _name: project)

    def test_empty_project_returns_json_field(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._service(Path(directory)).data("project")

        self.assertEqual("", result["raw_json"])
        self.assertNotIn("raw_yaml", result)
        self.assertEqual([], result["glossary"])

    def test_glossary_import_merges_existing_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "context.json").write_text(
                json.dumps({"index": 1}), encoding="utf-8"
            )
            (project / "glossary.txt").write_text(
                "旧 = Cũ\n", encoding="utf-8"
            )

            result = self._service(project).save(
                "project", {"glossary_text": "旧 = Đã sửa\n新 = Mới"}
            )

            self.assertEqual(2, result["imported"])
            self.assertEqual(
                {"旧": "Đã sửa", "新": "Mới"},
                {item["source"]: item["target"] for item in result["glossary"]},
            )

    def test_raw_json_is_saved_and_raw_yaml_remains_accepted(self):
        for field in ("raw_json", "raw_yaml"):
            with self.subTest(field), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                result = self._service(project).save(
                    "project",
                    {field: json.dumps({"index": 3, "glossary": "A = B"})},
                )

                self.assertEqual(3, result["index"])
                self.assertNotIn("raw_yaml", result)
                self.assertEqual("A = B", (project / "glossary.txt").read_text(encoding="utf-8").strip())

    def test_context_fields_refuse_accidental_glossary_wipe(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "context.json").write_text("{}", encoding="utf-8")
            (project / "glossary.txt").write_text("A = B\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "xóa toàn bộ glossary"):
                self._service(project).save(
                    "project",
                    {
                        "context_fields": {
                            "index": 0,
                            "glossary": "",
                        }
                    },
                )


if __name__ == "__main__":
    unittest.main()
