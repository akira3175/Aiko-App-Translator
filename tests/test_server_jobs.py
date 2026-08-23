import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import jobs


class TranslationLockTests(unittest.TestCase):
    def test_dead_process_lock_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "translation.lock"
            lock.write_text(json.dumps({"pid": 123, "kind": "pipeline"}), encoding="utf-8")
            with patch.object(jobs, "TRANSLATION_LOCK", lock), patch.object(
                jobs, "process_is_running", return_value=False
            ):
                self.assertIsNone(jobs.active_translation())
            self.assertFalse(lock.exists())

    def test_invalid_lock_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "translation.lock"
            lock.write_text("not-json", encoding="utf-8")
            with patch.object(jobs, "TRANSLATION_LOCK", lock):
                self.assertIsNone(jobs.active_translation())
            self.assertFalse(lock.exists())

    def test_live_process_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "translation.lock"
            expected = {"pid": 123, "kind": "pipeline"}
            lock.write_text(json.dumps(expected), encoding="utf-8")
            with patch.object(jobs, "TRANSLATION_LOCK", lock), patch.object(
                jobs, "process_is_running", return_value=True
            ):
                self.assertEqual(jobs.active_translation(), expected)
            self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
