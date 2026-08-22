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


if __name__ == "__main__":
    unittest.main()
