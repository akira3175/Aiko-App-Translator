import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import app


class PronounHistoryTests(unittest.TestCase):
    def test_edit_specific_history_record_preserves_other_record(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "pronouns.yaml"
            original = {
                "Alice|Bob": {
                    "characters": ["Alice", "Bob"],
                    "timeline": [
                        {
                            "chapter_number": 7,
                            "speaker": "Alice",
                            "listener": "Bob",
                            "speaker_self": "tôi",
                            "speaker_to_listener": "cậu",
                        },
                        {
                            "chapter_number": 7,
                            "speaker": "Bob",
                            "listener": "Alice",
                            "speaker_self": "anh",
                            "speaker_to_listener": "em",
                        },
                    ],
                }
            }
            path.write_text(
                yaml.safe_dump(original, allow_unicode=True), encoding="utf-8"
            )

            with patch.object(app, "safe_project", return_value=project):
                result = app.save_pronouns(
                    "project",
                    {
                        "key": "Alice|Bob",
                        "timeline_index": 0,
                        "expected_speaker": "Alice",
                        "expected_listener": "Bob",
                        "speaker_self": "mình",
                        "speaker_to_listener": "bạn",
                        "relationship_status": "Bạn bè",
                        "emotional_tone": "Thân thiện",
                        "locked": True,
                    },
                )

            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            timeline = saved["Alice|Bob"]["timeline"]
            self.assertEqual(
                (timeline[0]["speaker_self"], timeline[0]["speaker_to_listener"]),
                ("mình", "bạn"),
            )
            self.assertEqual(
                (timeline[1]["speaker_self"], timeline[1]["speaker_to_listener"]),
                ("anh", "em"),
            )
            self.assertEqual(timeline[0]["source"], "manual")
            self.assertTrue(saved["Alice|Bob"]["locked"])
            self.assertTrue(path.with_name("pronouns.yaml.bak").exists())
            self.assertEqual(result["pairs"][0]["timeline"][0]["record_index"], 0)


if __name__ == "__main__":
    unittest.main()
