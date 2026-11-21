import tempfile
import unittest
from pathlib import Path

from services.characters import CharacterService


class CharacterServiceTests(unittest.TestCase):
    def _service(self, project):
        return CharacterService(lambda _name: project)

    def test_save_counts_profiles_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            service = self._service(project)
            service.save("project", {"content": "## Alice\n\nMô tả"})
            result = service.save(
                "project", {"content": "## Alice\n\nMới\n\n## Bob\n\nMô tả"}
            )

            self.assertEqual(2, result["count"])
            self.assertTrue(result["backup"])
            self.assertTrue(result["content"].endswith("\n"))

    def test_existing_profile_cannot_be_wiped_accidentally(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "characters.md"
            path.write_text("## Alice\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "xóa sạch"):
                self._service(project).save("project", {"content": "  "})

    def test_structured_save_restore_and_snapshot_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            raw = project / "raw"
            raw.mkdir()
            (raw / "v1_c2_s1.md").write_text("# Ch2\n\nAlice gặp mặt.", encoding="utf-8")
            (raw / "v1_c5_s1.md").write_text("# Ch5\n\nAlice đột phá.", encoding="utf-8")

            service = self._service(project)
            first = service.save(
                "project",
                {
                    "expected_revision": 0,
                    "characters": [
                        {
                            "name": "Alice",
                            "fields": {
                                "status": [
                                    {"value": "Học đồ", "chapter": "v1_c1_s1.md", "confirmed": True},
                                    {"value": "Pháp sư", "chapter": "v1_c5_s1.md", "confirmed": False},
                                ]
                            },
                            "notes": [{"chapter": "v1_c5_s1.md", "text": "Thăng cấp cuối chương 5."}],
                        },
                        {
                            "name": "Bob",
                            "fields": {"status": [{"value": "Hiệp sĩ", "chapter": "v1_c1_s1.md"}]},
                        },
                    ],
                },
            )
            self.assertEqual(first["revision"], 1)
            self.assertEqual(first["chapters"], ["v1_c2_s1.md", "v1_c5_s1.md"])

            # Preview snapshot at v1_c5_s1.md filtered by chapter text: Alice only, pre-v1_c5 state!
            preview = service.preview_snapshot(
                "project", {"chapter": "v1_c5_s1.md", "filter_by_chapter_text": True}
            )
            self.assertEqual(preview["matched_count"], 1)
            self.assertTrue(preview["filtered_by_chapter_text"])
            self.assertIn("Học đồ", preview["markdown"])
            self.assertNotIn("Pháp sư", preview["markdown"])
            self.assertNotIn("Bob", preview["markdown"])

            # Preview unfiltered includes Bob too
            preview_all = service.preview_snapshot(
                "project", {"chapter": "v1_c5_s1.md", "filter_by_chapter_text": False}
            )
            self.assertEqual(preview_all["matched_count"], 2)
            self.assertIn("Bob", preview_all["markdown"])

            # Save revision 2 and restore backup back to revision 1 content
            second = service.save(
                "project",
                {"expected_revision": 1, "characters": [{"name": "Alice"}]},
            )
            self.assertEqual(second["count"], 1)
            self.assertTrue(second["backup"])

            restored = service.save("project", {"action": "restore_backup"})
            self.assertEqual(restored["count"], 2)
            self.assertEqual(restored["revision"], 3)

    def test_corrupt_utf8_json_triggers_recovery_required_and_restores_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            service = self._service(project)
            service.save("project", {"expected_revision": 0, "characters": [{"name": "Alice"}]})
            service.save("project", {"expected_revision": 1, "characters": [{"name": "Alice"}, {"name": "Bob"}]})

            # Corrupt characters.json with invalid UTF-8 bytes
            (project / "characters.json").write_bytes(b"\xff\xfe\x00broken")

            recovery = service.data("project")
            self.assertTrue(recovery.get("recovery_required"))
            self.assertTrue(recovery["backup"])
            self.assertEqual(recovery["characters"], [])

            restored = service.save("project", {"action": "restore_backup"})
            self.assertFalse(restored.get("recovery_required", False))
            self.assertEqual([c["name"] for c in restored["characters"]], ["Alice"])
            self.assertTrue(any(project.glob("characters.*.corrupt")))


if __name__ == "__main__":
    unittest.main()
