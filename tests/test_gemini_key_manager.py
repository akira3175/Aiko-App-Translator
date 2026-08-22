import json
import tempfile
import unittest
from pathlib import Path

from cores.gemini.key_manager import GeminiKeyManager


class GeminiKeyManagerTests(unittest.TestCase):
    def test_restores_active_key_by_fingerprint_after_reorder(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "current_key_fingerprint": GeminiKeyManager.fingerprint(
                            "second"
                        )
                    }
                ),
                encoding="utf-8",
            )
            manager = GeminiKeyManager(
                ["second", "first"], state, lambda **kwargs: kwargs
            )
            self.assertEqual(0, manager.current_index)
            self.assertEqual("second", manager.current_key)

    def test_rotation_persists_and_builds_client_with_new_key(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [0]
            manager = GeminiKeyManager(
                ["first", "second"],
                Path(directory) / "state.json",
                lambda **kwargs: kwargs,
                clock=lambda: now[0],
            )
            now[0] = 3600
            self.assertEqual({"api_key": "second"}, manager.get_client())
            restored = GeminiKeyManager(
                ["first", "second"],
                manager.state_file,
                lambda **kwargs: kwargs,
            )
            self.assertEqual("second", restored.current_key)


if __name__ == "__main__":
    unittest.main()
