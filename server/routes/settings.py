"""Settings, API-key, R19, update, browser, and AI-log HTTP routes."""

import json
import threading
import zipfile
from dataclasses import dataclass
from http import HTTPStatus


@dataclass(frozen=True)
class SettingsRoutes:
    configuration: object
    providers_payload: object
    update_payload: object
    prepare_update: object
    r19: object
    ai_logs: object
    clear_ai_logs: object
    open_app_browser: object
    active_translation: object

    def handle_get(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/settings":
            handler.json_response(self.configuration.settings_payload())
            return True
        if path == "/api/providers":
            handler.json_response({"items": self.providers_payload()})
            return True
        if path == "/api/ui-preferences":
            handler.json_response(self.configuration.ui_preferences())
            return True
        if path == "/api/update":
            try:
                handler.json_response(
                    self.update_payload(query.get("check", ["0"])[0] == "1")
                )
            except (ValueError, OSError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/gemini-api-keys":
            handler.json_response(self.configuration.api_keys_payload())
            return True
        if path == "/api/r19":
            handler.json_response(self.r19.payload(project))
            return True
        if path == "/api/ai-logs":
            try:
                handler.json_response(
                    self.ai_logs(project, query.get("limit", ["200"])[0])
                )
            except (ValueError, OSError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        return False

    def handle_post(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/ui-preferences":
            return self._json_call(
                handler,
                lambda: self.configuration.write_ui_preferences(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/ai-logs/clear":
            return self._json_call(
                handler,
                lambda: self.clear_ai_logs(project),
                (ValueError, OSError),
            )
        if path == "/api/settings":
            return self._json_call(
                handler,
                lambda: self.configuration.write_settings(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/app-browser/open":
            if not handler.is_loopback():
                handler.json_response(
                    {
                        "error": "Chỉ có thể mở Chrome trực tiếp trên máy đang chạy app."
                    },
                    HTTPStatus.FORBIDDEN,
                )
                return True
            return self._json_call(
                handler,
                self.open_app_browser,
                (ValueError, OSError),
            )
        if path == "/api/update":
            try:
                result = self.prepare_update()
                threading.Timer(0.8, handler.server.shutdown).start()
                handler.json_response(result)
            except (ValueError, OSError, zipfile.BadZipFile) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/gemini-api-keys":
            return self._json_call(
                handler,
                lambda: self.configuration.write_api_keys(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/gemini-api-keys/active":
            if self.active_translation():
                handler.json_response(
                    {"error": "Không thể đổi API key khi đang dịch"},
                    HTTPStatus.CONFLICT,
                )
                return True
            return self._json_call(
                handler,
                lambda: self.configuration.set_active_api_key(handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/gemini-api-keys/test":
            return self._json_call(
                handler,
                lambda: self.configuration.test_api_key(handler.body()),
                (ValueError, RuntimeError, OSError, json.JSONDecodeError),
            )
        if path == "/api/r19":
            return self._json_call(
                handler,
                lambda: self.r19.save(project, handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/r19/translate-word":
            return self._json_call(
                handler,
                lambda: self.r19.translate_word(project, handler.body()),
                (ValueError, OSError, json.JSONDecodeError, RuntimeError),
            )
        return False

    @staticmethod
    def _json_call(handler, action, errors):
        try:
            handler.json_response(action())
        except errors as exc:
            handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
