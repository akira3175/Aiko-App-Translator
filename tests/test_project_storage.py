import tempfile
import unittest
from pathlib import Path

import yaml

from cores.storage.project import load_context, load_json, migrate_project


class ProjectStorageTests(unittest.TestCase):
    def test_migrates_project_yaml_without_deleting_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            context = {"index": 12, "glossary": "原文 = Bản dịch", "style_notes": "Gọn"}
            (project / "context.yaml").write_text(
                yaml.safe_dump(context, allow_unicode=True), encoding="utf-8"
            )
            pronouns = {"A---B": {"locked": True, "timeline": []}}
            (project / "pronouns.yaml").write_text(
                yaml.safe_dump(pronouns, allow_unicode=True), encoding="utf-8"
            )
            (project / "char_index.yaml").write_text("char_index: 7\n", encoding="utf-8")

            migrated = migrate_project(project)

            self.assertEqual(load_context(project), context)
            self.assertEqual(load_json(project / "pronouns.json"), pronouns)
            self.assertEqual(
                load_json(project / "project_state.json"),
                {"schema_version": 1, "char_index": 7},
            )
            self.assertTrue((project / "context.yaml.legacy").exists())
            self.assertTrue((project / "pronouns.yaml.legacy").exists())
            self.assertFalse((project / "context.yaml").exists())
            self.assertEqual(len(migrated), 3)
            self.assertEqual(migrate_project(project), [])


if __name__ == "__main__":
    unittest.main()
