import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.launcher import LauncherService


class LauncherServiceTests(unittest.TestCase):
    def test_launcher_runtime_does_not_invoke_powershell(self):
        root = Path(__file__).resolve().parents[1]
        controller = (root / "launcher-wpf" / "LauncherController.cs").read_text(
            encoding="utf-8"
        )
        updater = (root / "launcher-wpf" / "PortableUpdater.cs").read_text(
            encoding="utf-8"
        )

        for marker in ("powershell.exe", "cmd.exe", "apply_update.ps1"):
            self.assertNotIn(marker, controller + updater)

    def test_prefers_bundled_launcher_and_marks_it_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local"
            executable = root / "Aiko-Launcher.exe"
            executable.write_bytes(b"exe")
            with patch.dict("os.environ", {"LOCALAPPDATA": str(local)}):
                service = LauncherService(root)

            self.assertEqual(
                {"available": True, "configured": False}, service.payload()
            )
            with patch("services.launcher.subprocess.Popen") as popen:
                service.open()
            popen.assert_called_once_with(
                [str(executable), f"--install-root={root}"], cwd=str(executable.parent)
            )
            self.assertEqual(
                {"available": True, "configured": True}, service.payload()
            )

    def test_falls_back_to_installed_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local"
            executable = local / "Aiko Launcher" / "Aiko-Launcher.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"exe")

            with patch.dict("os.environ", {"LOCALAPPDATA": str(local)}):
                service = LauncherService(root)

            self.assertEqual(executable, service.executable)
            self.assertTrue(service.payload()["available"])
            self.assertFalse(service.payload()["configured"])


if __name__ == "__main__":
    unittest.main()
