import unittest
from pathlib import Path
from unittest.mock import patch

from server.handler import create_handler


class _Dispatcher:
    def __init__(self, get=False, post=False, error=None):
        self.get_result = get
        self.post_result = post
        self.error = error
        self.calls = []

    def handle_get(self, handler, path, query):
        self.calls.append(("get", handler, path, query))
        if self.error:
            raise self.error
        return self.get_result

    def handle_post(self, handler, path, query):
        self.calls.append(("post", handler, path, query))
        if self.error:
            raise self.error
        return self.post_result


class _LanRoutes:
    def __init__(self, login=False, required=False):
        self.login = login
        self.required = required
        self.calls = []

    def handle_post(self, handler, path):
        self.calls.append(("post", path))
        return self.login

    def require(self, handler, api_request):
        self.calls.append(("require", api_request))
        return self.required

    def handle_get(self, handler, path):
        self.calls.append(("get", path))
        return False


class _LanAuth:
    @staticmethod
    def is_loopback(_address):
        return True


class _JobStream:
    def serve(self, *_args):
        return None


class ServerHandlerTests(unittest.TestCase):
    def _handler(self, dispatcher=None, lan_routes=None):
        dispatcher = dispatcher or _Dispatcher()
        lan_routes = lan_routes or _LanRoutes()
        handler_type = create_handler(
            dispatcher,
            lan_routes,
            _LanAuth(),
            _JobStream(),
            Path("web"),
            "1.2.3",
        )
        handler = object.__new__(handler_type)
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {}
        handler.responses = []
        handler.json_response = lambda payload, status=200: handler.responses.append(
            (status, payload)
        )
        return handler, dispatcher, lan_routes

    def test_get_passes_parsed_query_to_dispatcher(self):
        handler, dispatcher, _lan = self._handler(
            dispatcher=_Dispatcher(get=True)
        )
        handler.path = "/api/context?project=Demo"

        handler.do_GET()

        self.assertEqual("/api/context", dispatcher.calls[0][2])
        self.assertEqual(["Demo"], dispatcher.calls[0][3]["project"])

    def test_health_is_served_after_dispatchers_decline(self):
        handler, _dispatcher, _lan = self._handler()
        handler.path = "/api/health"

        handler.do_GET()

        self.assertEqual({"ok": True, "version": "1.2.3"}, handler.responses[0][1])

    def test_lan_login_runs_before_authorization(self):
        lan = _LanRoutes(login=True, required=True)
        handler, dispatcher, _lan = self._handler(lan_routes=lan)
        handler.path = "/api/lan/login"

        handler.do_POST()

        self.assertEqual([("post", "/api/lan/login")], lan.calls)
        self.assertEqual([], dispatcher.calls)

    def test_unexpected_post_error_returns_json_500(self):
        handler, _dispatcher, _lan = self._handler(
            dispatcher=_Dispatcher(error=RuntimeError("boom"))
        )
        handler.path = "/api/context"

        with patch("server.handler.traceback.print_exc") as printed:
            handler.do_POST()

        self.assertEqual(500, handler.responses[0][0])
        self.assertIn("boom", handler.responses[0][1]["error"])
        printed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
