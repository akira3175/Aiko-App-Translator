import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from split import chapter_splitter_novelpia_md as splitter


class _Response:
    headers = {"Content-Type": "image/jpeg"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"jpeg-data"


class RemoteImageTests(unittest.TestCase):
    def test_explicit_volume_titles_reset_chapter_numbers(self):
        documents = [
            ("intro", "内容简介", []),
            ("v1", "第一卷 讨伐", []),
            ("c1", "1", []),
            ("c2", "2", []),
            ("v2", "第二卷 再遇", []),
            ("c1b", "1 重逢", []),
            ("final", "终卷 交织的命运", []),
            ("final-c1", "1 最后", []),
        ]
        self.assertEqual(
            splitter.document_locations(documents, 1),
            [
                (0, 0), (1, 0), (1, 1), (1, 2),
                (2, 0), (2, 1), (3, 0), (3, 1),
            ],
        )

    def test_epub_without_volume_titles_keeps_legacy_numbering(self):
        documents = [("a", "Chương 1", []), ("b", "Chương 2", [])]
        self.assertEqual(splitter.document_locations(documents, 3), [(3, 0), (3, 1)])

    def test_downloads_legacy_sfacg_image_and_replaces_tag(self):
        elements = [{
            "type": "text",
            "content": "Trước\n[img=700,989]https://rss.sfacg.com/a.jpg[/img]\nSau",
        }]
        with tempfile.TemporaryDirectory() as folder, patch.object(
            splitter, "urlopen", return_value=_Response()
        ):
            result = splitter.localize_remote_images(elements, folder, "v0_c1", delay=0)
            image = next(item for item in result if item["type"] == "image")
            self.assertEqual(image["local_filename"], "v0_c1_remote_001.jpg")
            self.assertEqual((Path(folder) / image["local_filename"]).read_bytes(), b"jpeg-data")
            self.assertEqual([item["content"] for item in result if item["type"] == "text"], ["Trước", "Sau"])

    def test_failed_download_preserves_original_tag(self):
        tag = "[img=700,989]https://rss.sfacg.com/a.jpg[/img]"
        with tempfile.TemporaryDirectory() as folder, patch.object(
            splitter, "urlopen", side_effect=OSError("blocked")
        ):
            result = splitter.localize_remote_images(
                [{"type": "text", "content": tag}], folder, "v0_c1", delay=0
            )
            self.assertEqual(result, [{"type": "text", "content": tag}])

    def test_waits_between_attempts_even_after_failure(self):
        tags = (
            "[img]https://rss.sfacg.com/a.jpg[/img]"
            "[img]https://rss.sfacg.com/b.jpg[/img]"
        )
        with tempfile.TemporaryDirectory() as folder, patch.object(
            splitter, "urlopen", side_effect=OSError("blocked")
        ), patch.object(splitter.time, "sleep") as sleep:
            splitter.localize_remote_images(
                [{"type": "text", "content": tags}], folder, "v0_c1", delay=1
            )
            sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
