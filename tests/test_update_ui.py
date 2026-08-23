import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateUiTests(unittest.TestCase):
    def test_update_feature_only_references_existing_update_elements(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "features" / "updates.js").read_text(
            encoding="utf-8"
        )
        ids = set(re.findall(r'id="([^"]+)"', html))
        selectors = set(re.findall(r"\$\('#(update[A-Za-z0-9]+)'\)", script))

        self.assertTrue(selectors)
        self.assertEqual(set(), selectors - ids)
        self.assertIn("updateVersion", selectors)
        self.assertNotIn("updateCurrentVersion", script)
        self.assertNotIn("updateLatestVersion", script)


if __name__ == "__main__":
    unittest.main()
