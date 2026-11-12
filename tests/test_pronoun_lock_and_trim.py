"""Regression coverage for alias locks and inherited timeline state."""

import json
import tempfile
import unittest
from pathlib import Path

from cores.pronouns import load_pronouns, save_pronouns, update_pronoun_memory
from cores.pronouns.context import build_pair_states, collect_directions
from cores.pronouns.normalize import NameResolver, resolve_direction, trim_timeline


def record(chapter, **fields):
    return {
        "chapter_id": f"c{chapter}",
        "chapter_number": chapter,
        "speaker": "Alice",
        "listener": "Bob",
        "speaker_self": "",
        "speaker_to_listener": "",
        **fields,
    }


class AliasLockTests(unittest.TestCase):
    def test_alias_lock_blocks_updates_even_when_direct_pair_exists(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                path = project / "pronouns.json"
                (project / "characters.md").write_text(
                    "## Alice / Ally\n\n## Bob\n", encoding="utf-8"
                )
                memory = {}
                if duplicate:
                    memory["Alice---Bob"] = {
                        "characters": ["Alice", "Bob"],
                        "timeline": [record(2, speaker_self="new", speaker_to_listener="new")],
                    }
                memory["Ally---Bob"] = {
                    "characters": ["Ally", "Bob"],
                    "locked": True,
                    "timeline": [record(1, speaker="Ally", speaker_self="I", speaker_to_listener="you")],
                }
                save_pronouns(memory, path)
                count = update_pronoun_memory(
                    "c3", 3, "text", path, "test",
                    lambda _: json.dumps({"character_pairs": [
                        {"speaker": "Alice", "listener": "Bob", "speaker_self": "new"}
                    ]}),
                    sleep=lambda _: None,
                )
                self.assertEqual(count, 0)
                self.assertEqual(load_pronouns(path), memory)

    def test_locked_history_wins_over_newer_duplicate_per_direction(self):
        resolver = NameResolver([("Alice", ["Ally"]), ("Bob", [])])
        memory = {
            "alias": {"locked": True, "timeline": [
                record(1, speaker="Ally", speaker_self="I", speaker_to_listener="you")
            ]},
            "canonical": {"timeline": [
                record(2, speaker_self="new", speaker_to_listener="new"),
                record(2, speaker="Bob", listener="Alice", speaker_self="reverse"),
            ]},
        }
        directions = collect_directions(memory, resolver, before_chapter=3)
        state = resolve_direction(directions[("Alice", "Bob")])
        self.assertEqual((state["speaker_self"], state["speaker_to_listener"]), ("I", "you"))
        self.assertIn(("Bob", "Alice"), directions)
        self.assertTrue(build_pair_states(directions)[("Alice", "Bob")]["locked"])
        self.assertEqual(collect_directions(memory, resolver, before_chapter=1), {})


class TimelineAnchorTests(unittest.TestCase):
    def test_trim_preserves_effective_state_and_provenance(self):
        histories = [
            [record(1, speaker_self="I", speaker_to_listener="you")],
            [record(1, speaker_self="I"), record(2, speaker_to_listener="you")],
            [record(1, speaker_self="I", speaker_to_listener="you"),
             record(2, speaker_to_listener="sir", source="manual"),
             record(3, speaker_to_listener="sir")],
        ]
        for prefix in histories:
            with self.subTest(prefix=prefix):
                prefix.append(record(4, relationship_status="friends"))
                history = prefix + [record(n) for n in range(5, 22)]
                original = [dict(item) for item in history]
                trimmed = trim_timeline(history)
                self.assertEqual(resolve_direction(trimmed), resolve_direction(history))
                self.assertEqual(history, original)
                self.assertTrue(all(item in history for item in trimmed))
                self.assertEqual(trim_timeline(trimmed), trimmed)

    def test_recent_records_of_each_direction_survive(self):
        history = [record(n) for n in range(1, 22)] + [
            record(1, speaker="Bob", listener="Alice", speaker_self="reverse")
        ]
        trimmed = trim_timeline(history)
        self.assertEqual(len(trimmed), 16)
        self.assertTrue(any(item["speaker"] == "Bob" for item in trimmed))


if __name__ == "__main__":
    unittest.main()
