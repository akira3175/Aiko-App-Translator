import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.context.workflow import run_context_generation
from cores.storage.project import load_context, save_context


class ContextStorageTests(unittest.TestCase):
    def test_batch_overwrites_glossary_but_preserves_latest_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            raw = project / "raw"
            raw.mkdir()
            (raw / "v1_c1_s1.md").write_text("# Một\n\n原文", encoding="utf-8")
            save_context(project, {"index": 0, "glossary": "旧 = Cũ"})

            def generate(_batch, _old_glossary, instructions=None):
                save_context(project, {"index": 0, "glossary": "旧 = Đã sửa tay", "style_notes": "Ghi chú mới"})
                return "###START###\n新 = Mới\n###END###"

            with patch("cores.context.workflow.time.sleep"):
                run_context_generation(
                    engine_name="test",
                    setup_browser=None,
                    close_browser=None,
                    generate_glossary=generate,
                    raw_dir=str(raw),
                    context_file=str(project / "context.json"),
                    batch_size=1,
                )

            saved = load_context(project)
            self.assertEqual("新 = Mới", saved["glossary"])
            self.assertEqual("Ghi chú mới", saved["style_notes"])
            self.assertEqual(saved["index"], 1)


if __name__ == "__main__":
    unittest.main()
