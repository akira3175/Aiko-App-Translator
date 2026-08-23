import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.launcher import LauncherService


class LauncherServiceTests(unittest.TestCase):
    def test_reports_and_opens_unified_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local"
            executable = local / "Aiko Launcher" / "Aiko-Launcher.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"exe")
            with patch.dict("os.environ", {"LOCALAPPDATA": str(local)}):
                service = LauncherService(root)

            self.assertEqual(
                {"available": True, "configured": True}, service.payload()
            )
            with patch("services.launcher.subprocess.Popen") as popen:
                service.open()
            popen.assert_called_once_with(
                [str(executable), f"--install-root={root}"], cwd=str(executable.parent)
            )


if __name__ == "__main__":
    unittest.main()
