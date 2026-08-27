import subprocess
import sys
import unittest
from pathlib import Path


class EntrypointImportTests(unittest.TestCase):
    def test_context_entrypoint_imports_in_a_clean_process(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import cores.context.__main__; print('context-import-ok')",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("context-import-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
