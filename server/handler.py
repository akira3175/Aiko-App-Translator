"""Dependency-injected HTTP request handler for the local application."""

import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from server.http import download, json_body, json_response, serve_static


def create_handler(dispatcher, lan_routes, lan_auth, job_stream, web_root, app_version):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def json_response(self, payload, status=HTTPStatus.OK):
            return json_response(self, payload, status)

        def download_response(self, body, content_type, filename):
            return download(self, body, content_type, filename)

        def body(self):
            return json_body(self)

        def stream_job_events(self, job_key, after):
            return job_stream.serve(self, job_key, after)

        def is_loopback(self):
            return lan_auth.is_loopback(self.client_address[0])

        def require_lan_authorization(self, api_request=False):
            return lan_routes.require(self, api_request)

        def do_GET(self):
            parsed = urlparse(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            if self.require_lan_authorization(path.startswith("/api/")):
                return
            if dispatcher.handle_get(self, path, query):
                return
            if lan_routes.handle_get(self, path):
                return
            if path == "/api/health":
                return self.json_response({"ok": True, "version": app_version})
            return self.static(path)

        def do_POST(self):
            try:
                path = urlparse(self.path).path
                if lan_routes.handle_post(self, path):
                    return
                if self.require_lan_authorization(True):
                    return
                return self._do_POST()
            except Exception as exc:
                traceback.print_exc()
                try:
                    return self.json_response(
                        {"error": f"Server xử lý yêu cầu thất bại: {exc}"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return None

        def _do_POST(self):
            parsed = urlparse(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            if dispatcher.handle_post(self, path, query):
                return
            self.json_response({"error": "Không tìm thấy"}, HTTPStatus.NOT_FOUND)

        def static(self, path):
            return serve_static(self, path, web_root)

    return Handler
