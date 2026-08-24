import tempfile
import unittest
from pathlib import Path

from cores.storage.project import load_json
from services.cloudflare.sharing import _chapter_html, close, remove_chapter, save


class FakeR2Client:
    def __init__(self):
        self.uploads = []
        self.deletes = []

    def put_object(self, **request):
        self.uploads.append(request)
        return {}

    def delete_objects(self, **request):
        self.deletes.append(request)
        return {}


class PrivateSharingTests(unittest.TestCase):
    def test_shared_chapter_preserves_markdown_emphasis(self):
        with tempfile.TemporaryDirectory() as directory:
            output, images = _chapter_html(
                Path(directory),
                "Normal **Bold** *Italic* ***Both*** __Bold2__ _Italic2_",
                "share-id",
            )

        self.assertEqual(images, [])
        self.assertIn("<strong>Bold</strong>", output)
        self.assertIn("<em>Italic</em>", output)
        self.assertIn("<strong><em>Both</em></strong>", output)
        self.assertIn("<strong>Bold2</strong>", output)
        self.assertIn("<em>Italic2</em>", output)

    def test_save_remove_and_close_share(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "Truyện thử"
            translated = project / "translated"
            images = project / "image"
            translated.mkdir(parents=True)
            images.mkdir()
            (translated / "v1_c1_s1.md").write_text(
                "# Chương một\n\nĐoạn đầu\n\n![Ảnh](../image/a.png)",
                encoding="utf-8",
            )
            (translated / "v1_c1_s2.md").write_text(
                "# Segment hai\n\nĐoạn sau", encoding="utf-8"
            )
            (images / "a.png").write_bytes(b"image")
            config = {
                "bucket": "private-shares",
                "worker_url": "https://reader.example",
            }
            client = FakeR2Client()

            result = save(
                "Truyện thử",
                project,
                {
                    "title": "Bản đọc thử",
                    "chapters": ["v1_c1_s2.md", "v1_c1_s1.md"],
                    "expires_days": 7,
                },
                config,
                client,
            )

            stored = load_json(project / "sharing.json", {})["shares"][0]
            share_id = stored["id"]
            self.assertEqual(stored["chapters"][0]["name"], "v1_c1.md")
            self.assertEqual(stored["chapters"][0]["title"], "Chương một")
            self.assertNotIn("token", result["items"][0])
            self.assertIn(f"share={share_id}", result["items"][0]["url"])
            uploaded_keys = {request["Key"] for request in client.uploads}
            self.assertIn(f"shares/{share_id}/chapters/v1_c1.md", uploaded_keys)
            self.assertIn(f"shares/{share_id}/images/a.png", uploaded_keys)
            self.assertIn(f"shares/{share_id}/manifest.json", uploaded_keys)

            result = remove_chapter(
                project, share_id, "v1_c1.md", config, client
            )
            self.assertEqual(result["items"][0]["chapters"], [])
            result = close(project, share_id, config, client)
            self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
