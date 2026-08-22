import tempfile
import unittest
from pathlib import Path

from services.publishing import PublishingService


class _Configuration:
    setting_defaults = {"share_worker_url": ""}

    def __init__(self):
        self.saved = {}

    def saved_settings(self):
        return dict(self.saved)

    def write_settings(self, payload):
        self.saved = dict(payload["values"])
        return self.settings_payload()

    def settings_payload(self):
        return {"items": []}


class PublishingServiceTests(unittest.TestCase):
    def _service(self, root, project, configuration=None):
        configuration = configuration or _Configuration()
        return PublishingService(
            root=root,
            safe_project=lambda _name: project,
            configuration=configuration,
            provision_share_worker=lambda _payload, _root: {
                "settings": {"share_worker_url": "https://reader.example"},
                "worker": "ready",
            },
            provision_publishing_r2=lambda _payload: {
                "settings": {"r2_bucket": "books"},
                "bucket": "ready",
            },
        )

    def test_publishing_books_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            service = self._service(root, project)

            result = service.save(
                "project",
                {
                    "books": [
                        {"label": "Quyển 2", "book_id": "book=22", "volume": 2},
                        {"label": "Quyển 1", "book_id": "11", "volume": 1},
                    ]
                },
            )

            self.assertEqual([1, 2], [book["volume"] for book in result["books"]])
            self.assertTrue(result["exists"])

    def test_cloudflare_setup_updates_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            configuration = _Configuration()
            service = self._service(root, project, configuration)

            result = service.deploy_share_worker({})

            self.assertTrue(result["ok"])
            self.assertEqual("ready", result["worker"])
            self.assertEqual(
                "https://reader.example",
                configuration.saved["share_worker_url"],
            )


if __name__ == "__main__":
    unittest.main()
