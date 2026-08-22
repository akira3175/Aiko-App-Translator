"""Open the shared application Chrome profile for manual use."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppBrowserService:
    root: Path
    profile_path: Path
    jobs: dict
    active_translation: object
    chrome_binary: object
    popen: object = subprocess.Popen

    def open(self):
        if self.active_translation() or any(
            job.get("status") == "running" for job in self.jobs.values()
        ):
            raise ValueError(
                "Hãy chờ hoặc dừng tác vụ đang chạy trước khi mở Chrome của ứng dụng"
            )
        chrome = self.chrome_binary()
        if chrome is None:
            raise ValueError("Không tìm thấy Chrome hoặc Chromium đi kèm ứng dụng")
        self.profile_path.mkdir(parents=True, exist_ok=True)
        self.popen(
            [
                str(chrome),
                f"--user-data-dir={self.profile_path}",
                "--new-window",
                "https://www.google.com/",
            ],
            cwd=str(self.root),
        )
        return {"ok": True, "message": "Đã mở Chrome của ứng dụng"}
