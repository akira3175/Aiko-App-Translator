import subprocess
import unittest
from pathlib import Path


class FrontendRuntimeTests(unittest.TestCase):
    def test_app_modules_initialize_without_runtime_error(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "tests/frontend_runtime_check.mjs"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("runtime-import-ok", result.stdout)

    def test_web_review_hides_parallel_workers(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "web" / "features" / "pipeline.js").read_text(
            encoding="utf-8"
        )
        settings_script = (root / "web" / "features" / "settings.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("filter(([id])=>id!=='workers')", script)
        self.assertIn("config.workers=1", script)
        self.assertIn("xử lý tuần tự từng chương", script)
        self.assertIn("function render(nextItems)", settings_script)
        self.assertIn("let activeGroup='pipeline'", settings_script)
        self.assertIn("items=nextItems", settings_script)
        self.assertNotIn("items=items", settings_script)
        self.assertIn("const button=$('#savePythonSettings')", settings_script)
        self.assertIn("const button=$('#resetPythonSettings')", settings_script)
        self.assertNotIn("const button=$('#save')", settings_script)
        self.assertNotIn("const button=$('#reset')", settings_script)


if __name__ == "__main__":
    unittest.main()
