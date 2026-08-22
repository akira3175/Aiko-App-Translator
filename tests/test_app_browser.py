import tempfile
import unittest
from pathlib import Path

from services.app_browser import AppBrowserService


class AppBrowserServiceTests(unittest.TestCase):
    def service(self, root, **overrides):
        calls = overrides.pop("calls", [])

        def popen(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        values = {
            "root": root,
            "profile_path": root / "profile",
            "jobs": {},
            "active_translation": lambda: None,
            "chrome_binary": lambda: root / "chrome.exe",
            "popen": popen,
        }
        values.update(overrides)
        return AppBrowserService(**values)

    def test_open_uses_shared_profile_and_application_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            result = self.service(root, calls=calls).open()

            command = calls[0][0][0]
            self.assertEqual({"ok": True, "message": "Đã mở Chrome của ứng dụng"}, result)
            self.assertEqual(str(root / "chrome.exe"), command[0])
            self.assertIn(f"--user-data-dir={root / 'profile'}", command)
            self.assertEqual("https://www.google.com/", command[-1])
            self.assertEqual(str(root), calls[0][1]["cwd"])
            self.assertTrue((root / "profile").is_dir())

    def test_open_is_blocked_while_any_job_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            service = self.service(
                root,
                calls=calls,
                jobs={"review": {"status": "running"}},
            )

            with self.assertRaisesRegex(ValueError, "tác vụ đang chạy"):
                service.open()

            self.assertEqual([], calls)

    def test_open_is_blocked_while_translation_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(
                root, active_translation=lambda: {"kind": "pipeline"}
            )

            with self.assertRaisesRegex(ValueError, "tác vụ đang chạy"):
                service.open()

    def test_open_reports_missing_chrome_without_creating_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(root, chrome_binary=lambda: None)

            with self.assertRaisesRegex(ValueError, "Không tìm thấy Chrome"):
                service.open()

            self.assertFalse((root / "profile").exists())


if __name__ == "__main__":
    unittest.main()
