"""Regression tests for concurrent edits, reruns and locked prompt rules."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cores.pronouns import (
    format_pronoun_context,
    load_pronouns,
    save_pronouns,
    update_pronoun_memory,
)
from cores.pronouns.normalize import resolve_direction, trim_timeline
from cores.pronouns.storage import edit_pronouns
from services.pronouns import PronounService


def record(chapter, **fields):
    return {
        "chapter_id": f"c{chapter}", "chapter_number": chapter,
        "speaker": "Alice", "listener": "Bob",
        "speaker_self": "I", "speaker_to_listener": "you", **fields,
    }


def pair(timeline, **fields):
    return {"characters": ["Alice", "Bob"], "timeline": timeline, **fields}


def response(*records):
    return json.dumps({"character_pairs": list(records)})


class PronounUpdateRegressionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.project = Path(directory.name)
        self.path = self.project / "pronouns.json"
        self.service = PronounService(lambda _: self.project)

    def update(self, chapter, generate, model="test"):
        return update_pronoun_memory(
            f"c{chapter}", chapter, "text", self.path, model, generate,
            sleep=lambda _: None,
        )

    def test_edit_during_generation_survives_with_and_without_lock(self):
        for locked in (False, True):
            with self.subTest(locked=locked):
                save_pronouns({"Alice---Bob": pair([record(1)])}, self.path)

                def generate(_):
                    self.service.save("project", {
                        "key": "Alice---Bob", "speaker_self": "MANUAL",
                        "speaker_to_listener": "SIR", "locked": locked,
                    })
                    return response(record(1, speaker_self="AI"))

                self.update(1, generate)
                saved = load_pronouns(self.path)["Alice---Bob"]
                self.assertEqual(saved["locked"], locked)
                self.assertEqual(resolve_direction(saved["timeline"])["speaker_self"], "MANUAL")
                self.assertTrue(any(r.get("source") == "manual" for r in saved["timeline"]))

    def test_failed_or_disabled_extraction_never_writes_memory(self):
        original = {"Alice---Bob": pair([record(1)])}
        for text in (
            "", "not json", "{}", '{"character_pairs":null}',
            '{"character_pairs":{}}', '{"character_pairs":[{}]}',
            response(record(1), {"speaker": "Alice"}),
            response(record(1, speaker_self={"bad": "value"})),
        ):
            with self.subTest(text=text):
                save_pronouns(original, self.path)
                before = self.path.read_bytes()
                self.assertEqual(self.update(1, lambda _: text), 0)
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.update(1, lambda _: self.fail("disabled model called"), model="none"), 0)
        self.assertEqual(load_pronouns(self.path), original)

    def test_provider_failure_preserves_memory(self):
        original = {"Alice---Bob": pair([record(1)])}
        save_pronouns(original, self.path)

        def generate(_):
            raise RuntimeError("503 unavailable")

        self.assertEqual(self.update(1, generate), 0)
        self.assertEqual(load_pronouns(self.path), original)

    def test_empty_rerun_removes_ai_only_and_honors_alias_locks(self):
        (self.project / "characters.md").write_text("## Alice / Ally\n\n## Bob\n", encoding="utf-8")
        original = {
            "Alice---Bob": pair([record(1)]),
            "Ally---Bob": pair([record(1, speaker="Ally")], characters=["Ally", "Bob"], locked=True),
            "Other---Pair": pair([
                record(1, speaker="Other", listener="Pair"),
                record(2, speaker="Other", listener="Pair"),
                record(1, speaker="Other", listener="Pair", source="manual"),
            ], characters=["Other", "Pair"]),
            "Gone---Pair": pair([record(1, speaker="Gone", listener="Pair")], characters=["Gone", "Pair"]),
        }
        save_pronouns(original, self.path)
        self.update(1, lambda _: response())
        saved = load_pronouns(self.path)
        self.assertEqual(saved["Alice---Bob"], original["Alice---Bob"])
        self.assertEqual(saved["Ally---Bob"], original["Ally---Bob"])
        self.assertEqual(saved["Other---Pair"]["timeline"], original["Other---Pair"]["timeline"][1:])
        self.assertNotIn("Gone---Pair", saved)

    def test_rerun_replaces_pairs_missing_from_new_result(self):
        save_pronouns({"Alice---Bob": pair([record(1)])}, self.path)
        self.update(1, lambda _: response(record(1, listener="Carol")))
        saved = load_pronouns(self.path)
        self.assertNotIn("Alice---Bob", saved)
        self.assertEqual(list(saved), ["Alice---Carol"])

    def test_rerun_keeps_existing_alias_key_and_metadata(self):
        (self.project / "characters.md").write_text("## Alice / Ally\n\n## Bob\n", encoding="utf-8")
        save_pronouns({"Ally---Bob": pair(
            [record(1, speaker="Ally")], characters=["Ally", "Bob"], locked=False,
        )}, self.path)
        self.assertEqual(self.update(1, lambda _: response(record(1))), 1)
        saved = load_pronouns(self.path)
        self.assertEqual(list(saved), ["Ally---Bob"])
        self.assertIs(saved["Ally---Bob"]["locked"], False)
        self.assertEqual(len(saved["Ally---Bob"]["timeline"]), 1)

    def test_manual_confirmation_survives_trim_and_later_rerun(self):
        history = [record(1), record(2, source="manual")] + [
            record(n, speaker_self="", speaker_to_listener="") for n in range(3, 22)
        ]
        trimmed = trim_timeline(history)
        self.assertIn(history[1], trimmed)
        save_pronouns({"Alice---Bob": pair(trimmed)}, self.path)
        self.update(2, lambda _: response(record(2, speaker_self="AI", speaker_to_listener="AI")))
        saved = load_pronouns(self.path)["Alice---Bob"]["timeline"]
        self.assertIn(history[1], saved)
        self.assertEqual(resolve_direction(saved)["speaker_self"], "I")

    def test_locked_rules_survive_budget_and_rank_before_unlocked_rules(self):
        memory = {"Alice---Bob": pair([record(1)], locked=True)}
        names = ["Alice"]
        for n in range(10):
            a, b = f"Person{n}A", f"Person{n}B"
            names.extend([a, b])
            memory[f"{a}---{b}"] = pair([record(2, speaker=a, listener=b)], characters=[a, b])
        save_pronouns(memory, self.path)
        prompt = format_pronoun_context(3, self.path, glossary_names=names)
        self.assertIn("Alice ↔ Bob", prompt)
        self.assertLess(prompt.index("Alice ↔ Bob"), prompt.index("Person0A ↔ Person0B"))
        self.assertEqual(prompt.count("▸"), 10)

        for value in memory.values():
            value["locked"] = True
        save_pronouns(memory, self.path)
        prompt = format_pronoun_context(3, self.path, glossary_names=names)
        self.assertEqual(prompt.count("▸"), 11)

    def test_aborted_edit_does_not_commit_and_releases_lock(self):
        original = {"Alice---Bob": pair([record(1)])}
        save_pronouns(original, self.path)
        with self.assertRaises(ValueError):
            with edit_pronouns(self.path) as data:
                data.clear()
                raise ValueError("cancel")
        self.assertEqual(load_pronouns(self.path), original)
        self.service.save("p", {"key": "Alice---Bob", "action": "delete"})
        self.assertEqual(load_pronouns(self.path), {})

    def test_ui_and_ai_writers_wait_for_other_process_transaction(self):
        root = str(Path(__file__).resolve().parents[1])
        for writer in ("ui", "ai"):
            with self.subTest(writer=writer):
                save_pronouns({"Alice---Bob": pair([record(1)])}, self.path)
                child_code = f"""
import sys
sys.path.insert(0, {root!r})
from pathlib import Path
from cores.pronouns import update_pronoun_memory
from services.pronouns import PronounService
path = Path({str(self.path)!r})
print('ready', flush=True)
if {writer!r} == 'ui':
    PronounService(lambda _: path.parent).save('p', {{'key': 'Alice---Bob', 'speaker_self': 'manual', 'speaker_to_listener': 'sir', 'locked': True}})
else:
    update_pronoun_memory('c2', 2, 'text', path, 'test', lambda _: {response(record(2, speaker_self='AI'))!r}, sleep=lambda _: None)
"""
                process = None
                try:
                    with edit_pronouns(self.path) as data:
                        process = subprocess.Popen(
                            [sys.executable, "-c", child_code],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                        self.assertEqual(process.stdout.readline().strip(), "ready")
                        with self.assertRaises(subprocess.TimeoutExpired):
                            process.wait(timeout=0.2)
                        data["Other---Pair"] = pair([], characters=["Other", "Pair"])
                    stdout, stderr = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                finally:
                    if process is not None:
                        if process.poll() is None:
                            process.kill()
                        process.communicate()
                saved = load_pronouns(self.path)
                self.assertIn("Other---Pair", saved)
                if writer == "ui":
                    self.assertTrue(saved["Alice---Bob"]["locked"])
                else:
                    self.assertEqual(resolve_direction(saved["Alice---Bob"]["timeline"])["speaker_self"], "AI")


if __name__ == "__main__":
    unittest.main()
