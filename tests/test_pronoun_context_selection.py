"""Chapter relevance and manual corrections when translating a chapter again."""

import tempfile
import unittest
from pathlib import Path

from cores.context.selection import find_glossary_targets
from cores.pronouns import format_pronoun_context, save_pronouns
from cores.storage.project import save_context


def record(chapter, speaker="Alice", listener="Bob", **fields):
    return {
        "chapter_id": f"c{chapter}", "chapter_number": chapter,
        "speaker": speaker, "listener": listener,
        "speaker_self": "I", "speaker_to_listener": "you", **fields,
    }


def pair(chapter, speaker="Alice", listener="Bob", locked=False):
    return {
        "characters": [speaker, listener], "locked": locked,
        "timeline": [record(chapter, speaker, listener)],
    }


class PronounChapterContextTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        self.path = self.project / "pronouns.json"

    def test_unrelated_locks_do_not_use_slots_for_current_characters(self):
        memory = {"Alice---Bob": pair(2)}
        memory.update({f"other-{n}": pair(1, f"Other{n}A", f"Other{n}B", locked=True) for n in range(12)})
        save_pronouns(memory, self.path)
        prompt = format_pronoun_context(3, self.path, glossary_names=["Alice", "Bob"])
        self.assertIn("Alice ↔ Bob", prompt)
        self.assertNotIn("Other", prompt)
        self.assertEqual(prompt.count("▸"), 1)

    def test_known_characters_without_matching_history_return_empty_context(self):
        save_pronouns({"Alice---Bob": pair(1, locked=True)}, self.path)
        self.assertEqual(format_pronoun_context(3, self.path, glossary_names=["Carol"]), "")

    def test_unknown_characters_use_bounded_recent_history(self):
        memory = {"Alice---Bob": pair(20)}
        memory.update({f"other-{n}": pair(n, f"Other{n}A", f"Other{n}B", locked=True) for n in range(1, 13)})
        save_pronouns(memory, self.path)
        for names in (None, []):
            with self.subTest(names=names):
                prompt = format_pronoun_context(21, self.path, max_pairs=2, glossary_names=names)
                self.assertEqual(prompt.count("▸"), 2)
                self.assertIn("Alice ↔ Bob", prompt)
                self.assertIn("Other12A ↔ Other12B", prompt)
                self.assertNotIn("Other1A ↔ Other1B", prompt)

    def test_relevant_locked_pairs_rank_by_character_coverage(self):
        save_pronouns({
            "one": pair(2, "Alice", "Carol", locked=True),
            "both": pair(1, locked=True),
            "unlocked": pair(3, "Bob", "Dora"),
        }, self.path)
        prompt = format_pronoun_context(4, self.path, glossary_names=["Alice", "Bob", "Dora"])
        self.assertLess(prompt.index("Alice ↔ Bob"), prompt.index("Alice ↔ Carol"))
        self.assertLess(prompt.index("Alice ↔ Carol"), prompt.index("Bob ↔ Dora"))

    def test_current_manual_correction_applies_but_ai_and_future_records_do_not(self):
        for locked in (False, True):
            with self.subTest(locked=locked):
                data = pair(1, locked=locked)
                data["timeline"].extend([
                    record(2, source="manual", speaker_self="MANUAL", speaker_to_listener="SIR"),
                    record(2, speaker_self="CURRENT_AI"),
                    record(3, source="manual", speaker_self="FUTURE_MANUAL"),
                    record(3, "Bob", "Alice", speaker_self="FUTURE_AI"),
                ])
                save_pronouns({"Alice---Bob": data}, self.path)
                prompt = format_pronoun_context(2, self.path, glossary_names=["Alice", "Bob"])
                self.assertIn("Alice → Bob: tự xưng [MANUAL] | gọi đối phương [SIR]", prompt)
                self.assertNotIn("CURRENT_AI", prompt)
                self.assertNotIn("FUTURE", prompt)

    def test_manual_correction_applies_even_without_earlier_history(self):
        data = pair(1, locked=True)
        data["timeline"][0].update(source="manual", speaker_self="MANUAL")
        save_pronouns({"Alice---Bob": data}, self.path)
        self.assertIn("tự xưng [MANUAL]", format_pronoun_context(1, self.path))

    def test_current_ai_record_does_not_override_previous_history(self):
        data = pair(1)
        data["timeline"].append(record(2, speaker_self="CURRENT_AI"))
        save_pronouns({"Alice---Bob": data}, self.path)
        prompt = format_pronoun_context(2, self.path)
        self.assertIn("tự xưng [I]", prompt)
        self.assertNotIn("CURRENT_AI", prompt)

    def test_roster_character_without_pronoun_history_is_still_identified(self):
        (self.project / "characters.md").write_text("## Carol / Carrie\n", encoding="utf-8")
        save_context(self.project, {"glossary": "카롤 = Carrie"})
        save_pronouns({"Alice---Bob": pair(1, locked=True)}, self.path)
        names = find_glossary_targets(self.project / "context.json", "카롤", self.path)
        self.assertEqual(names, ["Carrie"])
        self.assertEqual(format_pronoun_context(3, self.path, glossary_names=names), "")

    def test_alias_match_keeps_only_relevant_locked_pair(self):
        (self.project / "characters.md").write_text("## Alice / Ally\n", encoding="utf-8")
        save_pronouns({
            "Alice---Bob": pair(1, locked=True),
            "Other---Pair": pair(2, "Other", "Pair", locked=True),
        }, self.path)
        prompt = format_pronoun_context(3, self.path, glossary_names=["Ally"])
        self.assertIn("Alice ↔ Bob", prompt)
        self.assertNotIn("Other ↔ Pair", prompt)


if __name__ == "__main__":
    unittest.main()
