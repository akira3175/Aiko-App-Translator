import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.importing import (
    ChapterImportService,
    cancel,
    confirm,
    create_preview,
    previews,
)


class ChapterImportServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "truyen" / "demo"
        self.raw = self.project / "raw"
        self.raw.mkdir(parents=True)
        self.runtime = self.root / ".runtime"
        previews.clear()

    def tearDown(self):
        previews.clear()
        self.temp_dir.cleanup()

    @staticmethod
    def _fake_splitter(_source, _volume, _base_dir, *, project_dir, **_kwargs):
        staging = Path(project_dir)
        raw = staging / "raw"
        image = staging / "image"
        raw.mkdir()
        image.mkdir()
        (raw / "v0_c0_s1.md").write_text(
            "# Chương mở đầu\n\nNội dung đầu.", encoding="utf-8"
        )
        (raw / "v0_c1_s1.md").write_text(
            "# Chương có ảnh\n\n![minh họa](../image/picture.jpg)",
            encoding="utf-8",
        )
        (image / "picture.jpg").write_bytes(b"image")
        return {"chapters": 2, "segments": 2, "metrics": ["characters"]}

    def test_preview_confirm_imports_selected_chapters_and_images(self):
        result = create_preview(
            "demo",
            self.project,
            self.raw,
            self.runtime,
            "epub",
            5000,
            b"epub-content",
            splitter=self._fake_splitter,
        )
        token = result["token"]
        staging = previews[token]["staging"]

        self.assertEqual([0, 1], [item["source_index"] for item in result["chapters"]])
        confirmed = confirm(
            "demo",
            self.project,
            self.raw,
            {
                "token": token,
                "source_from": 0,
                "source_to": 1,
                "target_volume": 2,
                "target_start": 10,
                "conflict": "skip",
                "selected": [0, 1],
            },
        )

        self.assertEqual(2, confirmed["imported"])
        self.assertTrue((self.raw / "v2_c10_s1.md").is_file())
        self.assertTrue((self.raw / "v2_c11_s1.md").is_file())
        self.assertEqual(b"image", (self.project / "image" / "picture.jpg").read_bytes())
        self.assertNotIn(token, previews)
        self.assertFalse(staging.exists())

    def test_preview_without_anchors_uses_next_volume_and_imports_from_zero(self):
        for filename in ("v3_c85_s1.md", "v12_c4_s1.md"):
            (self.raw / filename).write_text("# Unrelated\n\nabcdefghxyz", encoding="utf-8")
        result = create_preview(
            "demo", self.project, self.raw, self.runtime, "epub", 5000,
            b"content", splitter=self._fake_splitter,
        )
        self.assertEqual(0, result["anchors"])
        self.assertEqual((13, 0), (result["target_volume"], result["target_start"]))
        confirmed = confirm("demo", self.project, self.raw, {
            "token": result["token"], "source_from": result["source_from"],
            "source_to": result["source_to"], "target_volume": result["target_volume"],
            "target_start": result["target_start"], "selected": [0, 1], "conflict": "skip",
        })
        self.assertEqual(2, confirmed["imported"])
        self.assertTrue((self.raw / "v13_c0_s1.md").is_file())
        self.assertTrue((self.raw / "v13_c1_s1.md").is_file())
        self.assertEqual("# Unrelated\n\nabcdefghxyz", (self.raw / "v12_c4_s1.md").read_text(encoding="utf-8"))

    def test_preview_empty_project_starts_at_volume_one(self):
        result = create_preview(
            "demo", self.project, self.raw, self.runtime, "txt", 5000,
            b"content", splitter=self._fake_splitter,
        )
        self.assertEqual(0, result["anchors"])
        self.assertEqual((1, 0), (result["target_volume"], result["target_start"]))

    def test_preview_with_anchor_continues_matching_volume(self):
        fixture = self.root / "fixture"
        fixture.mkdir()
        self._fake_splitter(None, None, None, project_dir=fixture)
        (self.raw / "v3_c85_s1.md").write_bytes((fixture / "raw" / "v0_c0_s1.md").read_bytes())
        (self.raw / "v12_c4_s1.md").write_text("# Unrelated\n\nabcdefghxyz", encoding="utf-8")
        result = create_preview(
            "demo", self.project, self.raw, self.runtime, "epub", 5000,
            b"content", splitter=self._fake_splitter,
        )
        self.assertEqual(1, result["anchors"])
        self.assertEqual((3, 86), (result["target_volume"], result["target_start"]))
        self.assertEqual(1, result["source_from"])

    def test_cancel_removes_preview_and_staging(self):
        result = create_preview(
            "demo",
            self.project,
            self.raw,
            self.runtime,
            "txt",
            5000,
            b"text-content",
            splitter=self._fake_splitter,
        )
        token = result["token"]
        staging = previews[token]["staging"]

        self.assertEqual({"ok": True}, cancel(token))
        self.assertNotIn(token, previews)
        self.assertFalse(staging.exists())

    def test_bound_service_resolves_project_paths_for_preview(self):
        library = SimpleNamespace(
            safe_project=lambda _name: self.project,
            project_folders=lambda _name: (self.raw, self.project / "translated"),
        )
        service = ChapterImportService(self.runtime, library)

        with patch(
            "services.importing.service.create_preview",
            return_value={"token": "test"},
        ) as create:
            result = service.preview("demo", "epub", 5000, b"content")

        self.assertEqual({"token": "test"}, result)
        create.assert_called_once_with(
            "demo",
            self.project,
            self.raw,
            self.runtime,
            "epub",
            5000,
            b"content",
        )

    def test_bound_service_resolves_project_paths_for_confirm(self):
        library = SimpleNamespace(
            safe_project=lambda _name: self.project,
            project_folders=lambda _name: (self.raw, self.project / "translated"),
        )
        service = ChapterImportService(self.runtime, library)
        payload = {"token": "test"}

        with patch(
            "services.importing.service.confirm", return_value={"ok": True}
        ) as confirm_call:
            result = service.confirm("demo", payload)

        self.assertEqual({"ok": True}, result)
        confirm_call.assert_called_once_with("demo", self.project, self.raw, payload)


if __name__ == "__main__":
    unittest.main()
