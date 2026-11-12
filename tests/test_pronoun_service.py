import json
import tempfile
import unittest
from pathlib import Path

from cores.pronouns import load_pronouns, save_pronouns, update_pronoun_memory
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


class PronounEditorRevisionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        self.path = self.project / "pronouns.json"
        self.service = PronounService(lambda _: self.project)
        save_pronouns({"Alice---Bob": {
            "characters": ["Alice", "Bob"],
            "timeline": [
                {"chapter_id": f"c{n}", "chapter_number": n,
                 "speaker": "Alice", "listener": "Bob",
                 "speaker_self": "I", "speaker_to_listener": "you"}
                for n in (1, 2, 3)
            ],
        }}, self.path)

    def payload(self):
        pair = self.service.data("p")["pairs"][0]
        return {
            "key": pair["key"], "timeline_index": 1,
            "expected_revision": pair["revision"],
            "expected_speaker": "Alice", "expected_listener": "Bob",
            "speaker_self": "MANUAL", "speaker_to_listener": "SIR",
        }

    def assert_stale(self, payload):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "đã thay đổi"):
            self.service.save("p", payload)
        self.assertEqual(self.path.read_bytes(), before)

    def test_removed_chapter_cannot_shift_editor_to_another_chapter(self):
        payload = self.payload()
        update_pronoun_memory(
            "c1", 1, "text", self.path, "test",
            lambda _: '{"character_pairs":[]}', sleep=lambda _: None,
        )
        self.assert_stale(payload)

    def test_same_position_with_changed_record_is_rejected(self):
        payload = self.payload()
        memory = load_pronouns(self.path)
        memory["Alice---Bob"]["timeline"][1]["speaker_self"] = "CHANGED"
        save_pronouns(memory, self.path)
        self.assert_stale(payload)

    def test_changed_pair_lock_is_rejected(self):
        payload = self.payload()
        memory = load_pronouns(self.path)
        memory["Alice---Bob"]["locked"] = True
        save_pronouns(memory, self.path)
        self.assert_stale(payload)

    def test_indexed_edit_requires_revision(self):
        payload = self.payload()
        del payload["expected_revision"]
        self.assert_stale(payload)

    def test_valid_revision_edits_only_selected_chapter(self):
        payload = self.payload()
        before = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        result = self.service.save("p", payload)
        timeline = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        self.assertEqual(timeline[0], before[0])
        self.assertEqual(timeline[2], before[2])
        self.assertEqual(timeline[1]["chapter_id"], "c2")
        self.assertEqual(timeline[1]["speaker_self"], "MANUAL")
        self.assertNotEqual(result["pairs"][0]["revision"], payload["expected_revision"])

    def test_unrelated_pair_change_does_not_invalidate_editor(self):
        payload = self.payload()
        memory = load_pronouns(self.path)
        memory["Other---Pair"] = {"characters": ["Other", "Pair"], "timeline": []}
        save_pronouns(memory, self.path)
        self.service.save("p", payload)
        self.assertIn("Other---Pair", load_pronouns(self.path))

    def test_delete_checks_revision_too(self):
        payload = self.payload()
        memory = load_pronouns(self.path)
        memory["Alice---Bob"]["locked"] = True
        save_pronouns(memory, self.path)
        self.assert_stale({
            "key": payload["key"], "action": "delete",
            "expected_revision": payload["expected_revision"],
        })


if __name__ == "__main__":
    unittest.main()
