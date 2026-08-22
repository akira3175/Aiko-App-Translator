import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from services.updating import checker, downloader, installer


class _Response(io.BytesIO):
    def __init__(self, content):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class UpdateServiceTests(unittest.TestCase):
    def test_checker_parses_new_release_and_verified_asset(self):
        checksum = "a" * 64
        release = json.dumps(
            {
                "tag_name": "v1.2.0",
                "body": "Release notes",
                "html_url": "https://github.com/example/release",
                "assets": [
                    {
                        "name": "app.zip",
                        "browser_download_url": "https://example.com/app.zip",
                        "digest": f"sha256:{checksum}",
                    }
                ],
            }
        ).encode()

        result = checker.payload(
            True,
            "1.1.0",
            "owner/repo",
            "https://api.github.com/releases/latest",
            "app.zip",
            opener=lambda *_args, **_kwargs: _Response(release),
        )

        self.assertTrue(result["update_available"])
        self.assertTrue(result["download_ready"])
        self.assertEqual(checksum, result["sha256"])

    def test_archive_validation_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("NovelTranslatorStudio/../outside.txt", "bad")

            with self.assertRaisesRegex(ValueError, "không an toàn"):
                downloader.validate_archive(archive_path, "1.2.0")

    def test_download_checks_sha256_before_promoting_partial_file(self):
        content = b"portable archive"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "app.zip"
            result = downloader.download(
                {
                    "download_url": "https://example.com/app.zip",
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                destination,
                "1.1.0",
                opener=lambda *_args, **_kwargs: _Response(content),
            )

            self.assertEqual(destination, result)
            self.assertEqual(content, destination.read_bytes())
            self.assertFalse(destination.with_suffix(".zip.part").exists())

    def test_installer_requires_portable_runtime_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "bản portable"):
                installer.prepare(
                    root,
                    root / "updates",
                    "app.zip",
                    root / "apply_update.ps1",
                    "1.0.0",
                    {},
                    lambda _remote: self.fail("must not check network"),
                    lambda *_args: None,
                )


if __name__ == "__main__":
    unittest.main()
