import io
import unittest

from server.lan.auth import LanAuth
from server.lan.routes import LanRoutes


class _Handler:
    def __init__(self, address="192.168.1.20", body=None):
        self.client_address = (address, 12345)
        self.request_body = body or {}
        self.headers = {}
        self.responses = []
        self.sent_status = None
        self.sent_headers = []
        self.wfile = io.BytesIO()

    def body(self):
        return self.request_body

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))

    def send_response(self, status):
        self.sent_status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        return None


class LanAuthTests(unittest.TestCase):
    def test_loopback_is_always_authorized(self):
        auth = LanAuth(lambda: (False, ""))
        self.assertTrue(auth.authorized("127.0.0.1"))
        self.assertTrue(auth.authorized("::1"))

    def test_eleventh_failed_attempt_is_rate_limited_for_five_minutes(self):
        now = [1000.0]
        auth = LanAuth(lambda: (True, "123456"), clock=lambda: now[0])

        for _ in range(10):
            status, _payload, _token = auth.login("192.168.1.20", "wrong")
            self.assertEqual(401, status)
        status, payload, _token = auth.login("192.168.1.20", "123456")
        self.assertEqual(429, status)
        self.assertIn("5 phút", payload["error"])

        now[0] += 301
        status, _payload, token = auth.login("192.168.1.20", "123456")
        self.assertEqual(200, status)
        self.assertTrue(token)

    def test_successful_login_sets_secure_session_cookie(self):
        auth = LanAuth(lambda: (True, "123456"), token_factory=lambda: "token-1")
        routes = LanRoutes(auth, lambda: "0.0.0.0", 8765, lambda: "192.168.1.5")
        handler = _Handler(body={"pin": "123456"})

        self.assertTrue(routes.handle_post(handler, "/api/lan/login"))

        cookie = dict(handler.sent_headers)["Set-Cookie"]
        self.assertEqual(200, handler.sent_status)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertTrue(
            auth.authorized("192.168.1.20", "nts_lan_session=token-1")
        )

    def test_status_hides_pin_from_non_loopback_client(self):
        auth = LanAuth(lambda: (True, "123456"))
        routes = LanRoutes(auth, lambda: "0.0.0.0", 8765, lambda: "192.168.1.5")
        remote = _Handler()
        local = _Handler(address="127.0.0.1")

        routes.handle_get(remote, "/api/lan/status")
        routes.handle_get(local, "/api/lan/status")

        self.assertEqual("", remote.responses[0][1]["pin"])
        self.assertEqual("123456", local.responses[0][1]["pin"])


if __name__ == "__main__":
    unittest.main()
