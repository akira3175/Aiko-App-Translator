"""Open the Windows launcher and report first-run setup state."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class LauncherService:
    def __init__(self, root):
        self.root = root
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.executable = local / "Aiko Launcher" / "Aiko-Launcher.exe"

    def payload(self):
        available = self.executable.is_file()
        return {
            "available": available,
            "configured": available,
        }

    def open(self):
        if not self.executable.is_file():
            raise ValueError("Không tìm thấy Aiko Launcher")
        subprocess.Popen(
            [str(self.executable), f"--install-root={self.root}"],
            cwd=str(self.executable.parent),
        )
        return {"ok": True, "message": "Đã mở bảng điều khiển launcher."}
