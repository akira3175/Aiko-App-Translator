import tempfile
import unittest
from pathlib import Path

from services.sharing import SharingService


class _Configuration:
    setting_defaults = {
        "share_r2_account_id": "",
        "share_r2_access_key_id": "",
        "share_r2_secret_access_key": "",
        "share_r2_bucket": "private-shares",
        "share_worker_url": "",
    }

    def __init__(self, saved=None):
        self.saved = saved or {}

    def saved_settings(self):
        return dict(self.saved)


class _Boto3:
    def __init__(self):
        self.calls = []

    def client(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "client"


class SharingServiceTests(unittest.TestCase):
    def test_data_does_not_require_r2_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            service = SharingService(
                configuration=_Configuration(
                    {
                        "share_worker_url": "https://reader.example/",
                        "share_r2_bucket": "private-shares",
                    }
                ),
                safe_project=lambda _name: project,
                boto3_module=None,
            )

            result = service.data("project")

            self.assertTrue(result["configured"])
            self.assertEqual([], result["items"])

    def test_config_builds_r2_client_without_exposing_credentials(self):
        boto3 = _Boto3()
        service = SharingService(
            configuration=_Configuration(
                {
                    "share_r2_account_id": "account",
                    "share_r2_access_key_id": "access",
                    "share_r2_secret_access_key": "secret",
                }
            ),
            safe_project=lambda _name: Path("project"),
            boto3_module=boto3,
        )

        config = service.config()
        client = service.client(config)

        self.assertEqual("client", client)
        self.assertEqual(
            "https://account.r2.cloudflarestorage.com",
            boto3.calls[0][1]["endpoint_url"],
        )

    def test_missing_credentials_are_rejected(self):
        service = SharingService(
            configuration=_Configuration(),
            safe_project=lambda _name: Path("project"),
            boto3_module=None,
        )
        with self.assertRaisesRegex(ValueError, "Chưa cấu hình đầy đủ"):
            service.config()


if __name__ == "__main__":
    unittest.main()
