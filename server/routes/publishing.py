"""Publishing, Hako, Cloudflare, R2, and private-share HTTP routes."""

import json
from dataclasses import dataclass
from http import HTTPStatus

@dataclass(frozen=True)
class PublishingRoutes:
    publishing: object
    sharing: object

    def handle_get(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/publishing":
            return self._json_call(
                handler,
                lambda: self.publishing.data(project),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/hako/chapters":
            return self._json_call(
                handler,
                lambda: self.publishing.hako_chapters(query.get("url", [""])[0]),
                (ValueError,),
            )
        if path == "/api/shares":
            return self._json_call(
                handler,
                lambda: self.sharing.data(project),
                (ValueError, OSError, json.JSONDecodeError),
            )
        return False

    def handle_post(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/share-worker/deploy":
            if not self._require_loopback(handler):
                return True
            return self._json_call(
                handler,
                lambda: self.publishing.deploy_share_worker(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/publishing-r2/setup":
            if not self._require_loopback(handler):
                return True
            return self._json_call(
                handler,
                lambda: self.publishing.setup_publishing_r2(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/publishing":
            return self._json_call(
                handler,
                lambda: self.publishing.save(project, handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/shares":
            try:
                handler.json_response(self.sharing.save(project, handler.body()))
            except Exception as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        return False

    @staticmethod
    def _require_loopback(handler):
        if handler.is_loopback():
            return True
        handler.json_response(
            {
                "error": "Chỉ được thiết lập Cloudflare trực tiếp trên máy đang chạy app."
            },
            HTTPStatus.FORBIDDEN,
        )
        return False

    @staticmethod
    def _json_call(handler, action, errors):
        try:
            handler.json_response(action())
        except errors as exc:
            handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
