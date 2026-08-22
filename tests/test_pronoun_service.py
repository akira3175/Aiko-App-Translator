import json
import tempfile
import unittest
from pathlib import Path

from services.pronouns import PronounService


class PronounServiceTests(unittest.TestCase):
    def _service(self, project):
        return PronounService(lambda _name: project)

    def test_data_sorts_pairs_and_preserves_record_indexes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "pronouns.json").write_text(
                json.dumps(
                    {
                        "A|B": {
                            "characters": ["A", "B"],
                            "timeline": [
                                {"chapter_number": 5},
                                {"chapter_number": 2},
                            ],
                        },
                        "C|D": {
                            "characters": ["C", "D"],
                            "timeline": [{"chapter_number": 9}],
                            "locked": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = self._service(project).data("project")

            self.assertEqual(["C|D", "A|B"], [pair["key"] for pair in result["pairs"]])
            self.assertEqual(
                [1, 0],
                [item["record_index"] for item in result["pairs"][1]["timeline"]],
            )
            self.assertEqual(1, result["locked_count"])
            self.assertIn('"A|B"', result["raw_json"])
            self.assertNotIn("raw_yaml", result)

    def test_stale_expected_characters_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "pronouns.json").write_text(
                json.dumps(
                    {
                        "A|B": {
                            "timeline": [
                                {
                                    "chapter_number": 1,
                                    "speaker": "A",
                                    "listener": "B",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "đã thay đổi"):
                self._service(project).save(
                    "project",
                    {
                        "key": "A|B",
                        "expected_speaker": "B",
                        "speaker_self": "tôi",
                        "speaker_to_listener": "cậu",
                    },
                )

    def test_delete_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "pronouns.json"
            path.write_text(
                json.dumps({"A|B": {"timeline": [{"chapter_number": 1}]}}),
                encoding="utf-8",
            )

            result = self._service(project).save(
                "project", {"key": "A|B", "action": "delete"}
            )

            self.assertEqual(0, result["count"])
            self.assertTrue(path.with_name("pronouns.json.bak").exists())


if __name__ == "__main__":
    unittest.main()
