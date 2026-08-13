import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores import data_paths


class DataMigrationTests(unittest.TestCase):
    def test_moves_legacy_user_files_into_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            (root / "apikeys.txt").write_text("secret-key\n", encoding="utf-8")
            (root / "r19_words.txt").write_text("raw = translated\n", encoding="utf-8")
            with patch.multiple(
                data_paths,
                ROOT=root,
                DATA_DIR=data,
                GEMINI_API_KEYS_FILE=data / "apikeys.txt",
                R19_WORDS_FILE=data / "r19_words.txt",
            ):
                moved = data_paths.ensure_user_data_migrated()
            self.assertEqual(len(moved), 2)
            self.assertFalse((root / "apikeys.txt").exists())
            self.assertFalse((root / "r19_words.txt").exists())
            self.assertEqual((data / "apikeys.txt").read_text(encoding="utf-8"), "secret-key\n")
            self.assertEqual(
                (data / "r19_words.txt").read_text(encoding="utf-8"),
                "raw = translated\n",
            )

    def test_legacy_file_wins_over_fresh_release_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "apikeys.txt").write_text("", encoding="utf-8")
            (root / "apikeys.txt").write_text("user-key\n", encoding="utf-8")
            with patch.multiple(
                data_paths,
                ROOT=root,
                DATA_DIR=data,
                GEMINI_API_KEYS_FILE=data / "apikeys.txt",
                R19_WORDS_FILE=data / "r19_words.txt",
            ):
                data_paths.ensure_user_data_migrated()
            self.assertEqual((data / "apikeys.txt").read_text(encoding="utf-8"), "user-key\n")

    def test_accepts_singular_legacy_r19_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            (root / "r19_word.txt").write_text("term\n", encoding="utf-8")
            with patch.multiple(
                data_paths,
                ROOT=root,
                DATA_DIR=data,
                GEMINI_API_KEYS_FILE=data / "apikeys.txt",
                R19_WORDS_FILE=data / "r19_words.txt",
            ):
                data_paths.ensure_user_data_migrated()
            self.assertEqual((data / "r19_words.txt").read_text(encoding="utf-8"), "term\n")


if __name__ == "__main__":
    unittest.main()
