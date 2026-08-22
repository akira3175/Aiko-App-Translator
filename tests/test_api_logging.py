import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from cores.api_logging import log_api_call


class ApiLoggingTests(unittest.TestCase):
    def test_does_not_shadow_python_standard_logging(self):
        cores_dir = Path(__file__).resolve().parents[1] / "cores"
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(cores_dir)!r}); "
            "import logging; "
            "assert hasattr(logging, 'getLogger'); "
            "from selenium.webdriver.common.action_chains import ActionChains"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writes_unicode_jsonl_with_attachments(self):
        with tempfile.TemporaryDirectory() as directory:
            log_api_call(
                directory,
                threading.Lock(),
                "v1_c1_s1",
                "translate",
                "test-model",
                "提示",
                "Bản dịch",
                attachments=[{"name": "context.txt", "content": "xưng hô"}],
            )
            paths = list(Path(directory).glob("*.jsonl"))
            self.assertEqual(len(paths), 1)
            entry = json.loads(paths[0].read_text(encoding="utf-8").strip())
            self.assertEqual(entry["chapter_id"], "v1_c1_s1")
            self.assertEqual(entry["prompt_len"], 2)
            self.assertEqual(entry["attachments"][0]["content"], "xưng hô")

    def test_appends_multiple_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = threading.Lock()
            for chapter_id in ("c1", "c2"):
                log_api_call(directory, lock, chapter_id, "review", "model", "p", "r")
            path = next(Path(directory).glob("*.jsonl"))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
