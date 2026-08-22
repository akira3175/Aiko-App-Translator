import tempfile
import unittest
from pathlib import Path

from services.cloudflare.setup import deploy_share_worker, setup_publishing_r2


ACCOUNT_ID = "a" * 32
TOKEN_ID = "b" * 32


class CloudflareSetupTests(unittest.TestCase):
    def test_rejects_invalid_account_before_calling_api(self):
        with self.assertRaisesRegex(ValueError, "Account ID"):
            setup_publishing_r2(
                {"account_id": "bad", "api_token": "token", "bucket": "images"},
                api_call=lambda *args: self.fail("API must not be called"),
            )

    def test_publishing_setup_creates_bucket_and_returns_settings(self):
        calls = []

        def api_call(account_id, token, method, path, body=None, headers=None):
            calls.append((method, path, body))
            if path == "/user/tokens/verify":
                return {"id": TOKEN_ID}
            if path == "/r2/buckets":
                return {"buckets": []}
            if path.endswith("/domains/managed"):
                return {"domain": "images.example.dev"}
            return {}

        result = setup_publishing_r2(
            {"account_id": ACCOUNT_ID, "api_token": "secret", "bucket": "images"},
            api_call=api_call,
        )

        self.assertTrue(result["bucket_created"])
        self.assertEqual(result["public_url"], "https://images.example.dev")
        self.assertEqual(result["settings"]["r2_access_key_id"], TOKEN_ID)
        self.assertNotEqual(result["settings"]["r2_secret_access_key"], "secret")
        self.assertIn(("POST", "/r2/buckets", {"name": "images"}), calls)

    def test_worker_setup_uploads_source_and_returns_worker_url(self):
        calls = []

        def api_call(account_id, token, method, path, body=None, headers=None):
            calls.append((method, path, body, headers))
            if path == "/user/tokens/verify":
                return {"id": TOKEN_ID}
            if path == "/r2/buckets":
                return {"buckets": [{"name": "private-shares"}]}
            if path == "/workers/subdomain":
                return {"subdomain": "reader"}
            return {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cloudflare" / "share-worker" / "src" / "index.js"
            source.parent.mkdir(parents=True)
            source.write_text("export default {};", encoding="utf-8")
            result = deploy_share_worker(
                {
                    "account_id": ACCOUNT_ID,
                    "api_token": "secret",
                    "bucket": "private-shares",
                    "worker_name": "reader-worker",
                },
                root,
                api_call=api_call,
            )

        self.assertFalse(result["bucket_created"])
        self.assertEqual(
            result["worker_url"], "https://reader-worker.reader.workers.dev"
        )
        upload = next(call for call in calls if call[:2] == ("PUT", "/workers/scripts/reader-worker"))
        self.assertIn(b"export default {};", upload[2])
        self.assertIn("multipart/form-data", upload[3]["Content-Type"])


if __name__ == "__main__":
    unittest.main()
