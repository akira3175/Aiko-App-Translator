"""Open the Windows launcher and report first-run setup state."""

from __future__ import annotations

import subprocess


class LauncherService:
    def __init__(self, root):
        self.root = root
        self.executable = root / "Aiko App Translator.exe"
        self.configured_marker = root / ".runtime" / "launcher-shortcut-prompted"

    def payload(self):
        available = self.executable.is_file()
        return {
            "available": available,
            "configured": available and self.configured_marker.is_file(),
        }

    def open(self):
        if not self.executable.is_file():
            raise ValueError("Không tìm thấy Aiko App Translator.exe")
        subprocess.Popen(
            [str(self.executable), "--options-only"],
            cwd=str(self.root),
        )
        return {"ok": True, "message": "Đã mở bảng điều khiển launcher."}
