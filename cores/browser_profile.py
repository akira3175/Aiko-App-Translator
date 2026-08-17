"""Shared Chrome profile used by web automation and manual browsing."""

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent.parent
USER_DATA_ROOT = Path(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
) / "NovelTranslatorStudio"

# Preserve the existing ChatGPT login profile and let Gemini share it.
APP_BROWSER_PROFILE_PATH = USER_DATA_ROOT / "profiles" / "chatgpt"
PORTABLE_CHROME = APP_ROOT / "runtime" / "chromium" / "chrome-win64" / "chrome.exe"


def chrome_binary_path():
    candidates = [
        PORTABLE_CHROME,
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    return next((path for path in candidates if path.is_file()), None)
