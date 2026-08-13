"""Canonical paths and one-time migration for user-owned application data."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
GEMINI_API_KEYS_FILE = DATA_DIR / "apikeys.txt"
R19_WORDS_FILE = DATA_DIR / "r19_words.txt"


def _move_legacy_file(destination: Path, candidates):
    for source in candidates:
        source = Path(source)
        if not source.is_file() or source.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        return source
    return None


def ensure_user_data_migrated():
    """Move legacy root files into data/. Existing legacy data wins once."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    moved = []
    source = _move_legacy_file(GEMINI_API_KEYS_FILE, [ROOT / "apikeys.txt"])
    if source:
        moved.append((source, GEMINI_API_KEYS_FILE))
    source = _move_legacy_file(
        R19_WORDS_FILE,
        [ROOT / "r19_words.txt", ROOT / "r19_word.txt"],
    )
    if source:
        moved.append((source, R19_WORDS_FILE))
    GEMINI_API_KEYS_FILE.touch(exist_ok=True)
    return moved
