import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.routes.settings import SettingsRoutes


class _Handler:
    def __init__(self, body=None, loopback=True):
        self.request_body = body or {}
        self.loopback = loopback
        self.responses = []
        self.server = SimpleNamespace(shutdown=lambda: None)

    def body(self):
        return self.request_body

    def is_loopback(self):
        return self.loopback

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))


class SettingsRouteTests(unittest.TestCase):
    def _routes(self, **overrides):
        configuration = SimpleNamespace(
            settings_payload=lambda: {"items": []},
            write_settings=lambda _body: {"ok": True},
            ui_preferences=lambda: {"sidebar": {}},
            write_ui_preferences=lambda _body: {"sidebar": {}},
            api_keys_payload=lambda: {"keys": [], "count": 0},
            write_api_keys=lambda _body: {"count": 1},
            set_active_api_key=lambda _body: {"ok": True},
            test_api_key=lambda _body: {"ok": True},
        )
        values = {
            "configuration": configuration,
            "r19": SimpleNamespace(
                payload=lambda project: {"project": project},
                save=lambda project, _body: {"project": project},
                translate_word=lambda _project, _body: {"translation": "x"},
            ),
            "providers_payload": lambda: [{"id": "gemini-api"}],
            "update_payload": lambda remote: {"checked": remote},
            "prepare_update": lambda: {"ok": True},
            "update_progress": lambda: {"stage": "downloading"},
            "cancel_update": lambda: {"ok": True},
            "install_update": lambda: {"ok": True},
            "ai_logs": lambda _project, limit: {"limit": int(limit)},
            "clear_ai_logs": lambda _project: {"removed": 1},
            "open_app_browser": lambda: {"ok": True},
            "active_translation": lambda: None,
            "launcher": SimpleNamespace(
                payload=lambda: {"available": True, "configured": False},
                open=lambda: {"ok": True},
            ),
        }
        values.update(overrides)
        return SettingsRoutes(**values)

    def test_get_routes_dispatch_and_preserve_query(self):
        routes = self._routes()
        handler = _Handler()

        self.assertTrue(
            routes.handle_get(handler, "/api/update", {"check": ["1"]})
        )
        self.assertTrue(
            routes.handle_get(
                handler,
                "/api/ai-logs",
                {"project": ["Demo"], "limit": ["25"]},
            )
        )

        self.assertTrue(handler.responses[0][1]["checked"])
        self.assertEqual(25, handler.responses[1][1]["limit"])

    def test_active_key_is_blocked_while_translation_runs(self):
        called = []
        routes = self._routes(
            active_translation=lambda: {"kind": "pipeline"},
            configuration=SimpleNamespace(
                set_active_api_key=lambda _body: called.append(True)
            ),
        )
        handler = _Handler({"active_index": 1})

        self.assertTrue(
            routes.handle_post(handler, "/api/gemini-api-keys/active", {})
        )
        self.assertEqual(409, handler.responses[0][0])
        self.assertEqual([], called)

    def test_browser_open_requires_loopback(self):
        routes = self._routes()
        handler = _Handler(loopback=False)

        self.assertTrue(routes.handle_post(handler, "/api/app-browser/open", {}))
        self.assertEqual(403, handler.responses[0][0])

    def test_launcher_open_requires_loopback(self):
        routes = self._routes()
        handler = _Handler(loopback=False)

        self.assertTrue(routes.handle_post(handler, "/api/launcher/open", {}))
        self.assertEqual(403, handler.responses[0][0])

    def test_update_install_schedules_shutdown_after_success(self):
        scheduled = []
        routes = self._routes()
        handler = _Handler()

        class FakeTimer:
            def __init__(self, delay, callback):
                scheduled.append((delay, callback))

            def start(self):
                scheduled.append("started")

        with patch("server.routes.settings.threading.Timer", FakeTimer):
            self.assertTrue(routes.handle_post(handler, "/api/update/install", {}))

        self.assertEqual(0.8, scheduled[0][0])
        self.assertEqual("started", scheduled[1])
        self.assertTrue(handler.responses[0][1]["ok"])

    def test_server_shutdown_requires_loopback(self):
        handler = _Handler(loopback=False)

        self.assertTrue(
            self._routes().handle_post(handler, "/api/server/shutdown", {})
        )
        self.assertEqual(403, handler.responses[0][0])

    def test_server_shutdown_is_blocked_during_translation(self):
        handler = _Handler()
        routes = self._routes(active_translation=lambda: {"kind": "pipeline"})

        self.assertTrue(routes.handle_post(handler, "/api/server/shutdown", {}))
        self.assertEqual(409, handler.responses[0][0])

    def test_server_shutdown_is_scheduled_when_idle(self):
        scheduled = []
        handler = _Handler()

        class FakeTimer:
            def __init__(self, delay, callback):
                scheduled.append((delay, callback))

            def start(self):
                scheduled.append("started")

        with patch("server.routes.settings.threading.Timer", FakeTimer):
            self.assertTrue(
                self._routes().handle_post(handler, "/api/server/shutdown", {})
            )

        self.assertEqual(0.2, scheduled[0][0])
        self.assertEqual("started", scheduled[1])
        self.assertTrue(handler.responses[0][1]["ok"])

    def test_unknown_route_is_left_for_next_dispatcher(self):
        routes = self._routes()
        self.assertFalse(routes.handle_get(_Handler(), "/api/health", {}))
        self.assertFalse(routes.handle_post(_Handler(), "/api/jobs", {}))


if __name__ == "__main__":
    unittest.main()
