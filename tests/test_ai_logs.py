import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class AiLogTests(unittest.TestCase):
    def test_frontend_contains_drawer_and_log_controls(self):
        html = (app.WEB / "index.html").read_text(encoding="utf-8")
        script = (app.WEB / "app.js").read_text(encoding="utf-8")
        styles = (app.WEB / "ai-log.css").read_text(encoding="utf-8")
        self.assertIn('id="aiLogToggle"', html)
        self.assertIn('id="aiLogDrawer"', html)
        self.assertIn("/api/ai-logs?project=", script)
        self.assertIn("attachment-", script)
        self.assertIn("@media(max-width:650px)", styles)

    def test_reads_newest_logs_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            logs = library / "Demo" / "logs"
            logs.mkdir(parents=True)
            entries = [
                {
                    "ts": "2026-08-13T10:00:00",
                    "chapter_id": "v1_c1_s1",
                    "step": "translate",
                    "model": "test-model",
                    "ok": True,
                    "prompt": "old",
                    "response": "old response",
                },
                {
                    "ts": "2026-08-13T10:01:00",
                    "chapter_id": "v1_c2_s1",
                    "step": "polish",
                    "model": "test-model",
                    "ok": True,
                    "prompt": "Authorization: Bearer secret-value",
                    "response": "sk-abcdefghijklmnopqrstuvwxyz",
                    "attachments": [
                        {"name": "characters.md", "content": "AIzaabcdefghijklmnopqrstuvwxyz"}
                    ],
                },
            ]
            (logs / "2026-08-13.jsonl").write_text(
                "\n".join(json.dumps(item) for item in entries), encoding="utf-8"
            )
            with patch.object(app, "LIBRARY", library):
                result = app.ai_logs_data("Demo")
            self.assertEqual(result["items"][0]["chapter_id"], "v1_c2_s1")
            self.assertNotIn("secret-value", result["items"][0]["prompt"])
            self.assertEqual(result["items"][0]["response"], "[REDACTED]")
            self.assertEqual(
                result["items"][0]["attachments"][0]["content"], "[REDACTED]"
            )

    def test_clear_removes_only_jsonl_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            logs = library / "Demo" / "logs"
            logs.mkdir(parents=True)
            (logs / "one.jsonl").write_text("{}\n", encoding="utf-8")
            keep = logs / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with patch.object(app, "LIBRARY", library):
                result = app.clear_ai_logs("Demo")
            self.assertEqual(result["removed"], 1)
            self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
