"""Paths for the selected translation project and portable runtime."""

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = os.environ.get("NOVEL_PROJECT", "").strip()
PROJECT_DIR = Path("truyen") / PROJECT_NAME if PROJECT_NAME else Path("truyen")

PORTABLE_CHROME = APP_ROOT / "runtime" / "chromium" / "chrome-win64" / "chrome.exe"
PORTABLE_CHROMEDRIVER = (
    APP_ROOT / "runtime" / "chromium" / "chromedriver-win64" / "chromedriver.exe"
)
USER_DATA_ROOT = Path(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
) / "NovelTranslatorStudio"

NOVEL_TXT = PROJECT_DIR / "novel.txt"
CONTEXT_JSON = PROJECT_DIR / "context.json"
PRONOUNS_JSON = PROJECT_DIR / "pronouns.json"
REVIEW_JSON = PROJECT_DIR / "review.json"
MANUAL_CHECK_JSON = PROJECT_DIR / "manual_check.json"
CHARACTERS_MD = PROJECT_DIR / "characters.md"
LOG_DIR = PROJECT_DIR / "logs"
RAW_DIR = PROJECT_DIR / "raw"
TRANSLATED_DIR = PROJECT_DIR / "translated"
