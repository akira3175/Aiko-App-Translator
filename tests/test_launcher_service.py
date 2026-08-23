import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.launcher import LauncherService


class LauncherServiceTests(unittest.TestCase):
    def test_reports_first_run_and_opens_options_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Aiko App Translator.exe"
            executable.write_bytes(b"exe")
            service = LauncherService(root)

            self.assertEqual(
                {"available": True, "configured": False}, service.payload()
            )
            with patch("services.launcher.subprocess.Popen") as popen:
                service.open()
            popen.assert_called_once_with(
                [str(executable), "--options-only"], cwd=str(root)
            )

            marker = root / ".runtime" / "launcher-shortcut-prompted"
            marker.parent.mkdir()
            marker.write_text("1", encoding="utf-8")
            self.assertTrue(service.payload()["configured"])


if __name__ == "__main__":
    unittest.main()
