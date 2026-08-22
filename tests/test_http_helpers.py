import io
import json
import tempfile
import unittest
from pathlib import Path

from server.http import download, json_body, json_response, serve_static


class _Handler:
    def __init__(self, request=b""):
        self.headers = {"Content-Length": str(len(request))}
        self.rfile = io.BytesIO(request)
        self.wfile = io.BytesIO()
        self.status = None
        self.sent_headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        return None


class HttpHelperTests(unittest.TestCase):
    def test_json_request_and_response_preserve_unicode(self):
        request = json.dumps({"text": "原文"}, ensure_ascii=False).encode("utf-8")
        handler = _Handler(request)

        self.assertEqual({"text": "原文"}, json_body(handler))
        json_response(handler, {"translated": "bản dịch"})

        self.assertEqual(200, handler.status)
        self.assertEqual(
            {"translated": "bản dịch"},
            json.loads(handler.wfile.getvalue().decode("utf-8")),
        )
        self.assertEqual("no-store", dict(handler.sent_headers)["Cache-Control"])

    def test_download_uses_utf8_content_disposition(self):
        handler = _Handler()

        download(handler, b"book", "text/plain", "Truyện mới.txt")

        disposition = dict(handler.sent_headers)["Content-Disposition"]
        self.assertIn("filename*=UTF-8''", disposition)
        self.assertIn("Truy%E1%BB%87n%20m%E1%BB%9Bi.txt", disposition)

    def test_static_asset_and_spa_fallback_are_no_store(self):
        with tempfile.TemporaryDirectory() as directory:
            web = Path(directory)
            (web / "index.html").write_text("INDEX", encoding="utf-8")
            (web / "app.css").write_text("CSS", encoding="utf-8")
            asset = _Handler()
            fallback = _Handler()

            serve_static(asset, "/app.css", web)
            serve_static(fallback, "/missing/chapter", web)

        self.assertEqual(b"CSS", asset.wfile.getvalue())
        self.assertEqual(b"INDEX", fallback.wfile.getvalue())
        self.assertEqual(
            "no-store, max-age=0", dict(asset.sent_headers)["Cache-Control"]
        )

    def test_path_traversal_falls_back_and_unknown_api_returns_json_404(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / "web"
            web.mkdir()
            (web / "index.html").write_text("INDEX", encoding="utf-8")
            (root / "secret.txt").write_text("SECRET", encoding="utf-8")
            traversal = _Handler()
            api = _Handler()

            serve_static(traversal, "/../secret.txt", web)
            serve_static(api, "/api/unknown", web)

        self.assertEqual(b"INDEX", traversal.wfile.getvalue())
        self.assertEqual(404, api.status)
        self.assertEqual(
            "Không tìm thấy API",
            json.loads(api.wfile.getvalue().decode("utf-8"))["error"],
        )


if __name__ == "__main__":
    unittest.main()
