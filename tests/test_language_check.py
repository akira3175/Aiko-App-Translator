import tempfile
import unittest
from pathlib import Path

from cores.postprocess.language_check import save_manual_check_id
from cores.storage.project import load_json


class ManualCheckStorageTests(unittest.TestCase):
    def test_manual_check_is_saved_as_json_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_check.json"
            save_manual_check_id("v1_c1_s1", path)
            save_manual_check_id("v1_c1_s1", path)
            self.assertEqual(load_json(path, []), ["v1_c1_s1"])


if __name__ == "__main__":
    unittest.main()
