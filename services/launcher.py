"""Open the Windows launcher and report first-run setup state."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class LauncherService:
    def __init__(self, root):
        self.root = Path(root)
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        bundled = self.root / "Aiko-Launcher.exe"
        installed = local / "Aiko Launcher" / "Aiko-Launcher.exe"
        self.executable = bundled if bundled.is_file() else installed
        self.opened_marker = self.root / ".runtime" / "launcher-opened"

    def payload(self):
        available = self.executable.is_file()
        return {
            "available": available,
            "configured": self.opened_marker.is_file(),
        }

    def open(self):
        if not self.executable.is_file():
            raise ValueError("Không tìm thấy Aiko Launcher")
        subprocess.Popen(
            [str(self.executable), f"--install-root={self.root}"],
            cwd=str(self.executable.parent),
        )
        self.opened_marker.parent.mkdir(parents=True, exist_ok=True)
        self.opened_marker.write_text("opened\n", encoding="ascii")
        return {"ok": True, "message": "Đã mở bảng điều khiển launcher."}
