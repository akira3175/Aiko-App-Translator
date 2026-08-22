"""Static web assets with safe SPA fallback."""

import mimetypes
from http import HTTPStatus
from urllib.parse import unquote

from server.http.responses import json_response


def serve_static(handler, path, web_root):
    if path.startswith("/api/"):
        return json_response(
            handler, {"error": "Không tìm thấy API"}, HTTPStatus.NOT_FOUND
        )
    relative = "index.html" if path in ("", "/") else unquote(path.lstrip("/"))
    root = web_root.resolve()
    target = (web_root / relative).resolve()
    if root not in target.parents or not target.is_file():
        target = web_root / "index.html"
    data = target.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header(
        "Content-Type",
        mimetypes.guess_type(target.name)[0] or "application/octet-stream",
    )
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
