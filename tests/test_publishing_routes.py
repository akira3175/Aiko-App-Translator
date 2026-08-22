import unittest
from types import SimpleNamespace

from server.routes.publishing import PublishingRoutes


class _Handler:
    def __init__(self, body=None, loopback=True):
        self.request_body = body or {}
        self.loopback = loopback
        self.responses = []

    def body(self):
        return self.request_body

    def is_loopback(self):
        return self.loopback

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))


class PublishingRouteTests(unittest.TestCase):
    def _routes(self, **overrides):
        values = {
            "publishing": SimpleNamespace(
                data=lambda project: {"project": project},
                save=lambda project, _body: {"project": project},
                hako_chapters=lambda url: {"url": url},
                deploy_share_worker=lambda _body: {"ok": True},
                setup_publishing_r2=lambda _body: {"ok": True},
            ),
            "sharing": SimpleNamespace(
                data=lambda project: {"project": project, "items": []},
                save=lambda _project, _body: {"ok": True},
            ),
        }
        values.update(overrides)
        return PublishingRoutes(**values)

    def test_get_publishing_preserves_project_query(self):
        handler = _Handler()

        handled = self._routes().handle_get(
            handler, "/api/publishing", {"project": ["Demo"]}
        )

        self.assertTrue(handled)
        self.assertEqual("Demo", handler.responses[0][1]["project"])

    def test_cloudflare_setup_is_blocked_before_action_for_lan_client(self):
        calls = []
        publishing = self._routes().publishing
        publishing.deploy_share_worker = lambda body: calls.append(body)
        routes = self._routes(
            publishing=publishing
        )
        handler = _Handler({"api_token": "secret"}, loopback=False)

        handled = routes.handle_post(handler, "/api/share-worker/deploy", {})

        self.assertTrue(handled)
        self.assertEqual(403, handler.responses[0][0])
        self.assertEqual([], calls)

    def test_share_errors_keep_bad_request_status(self):
        def fail(_project, _body):
            raise RuntimeError("share failed")

        handler = _Handler()
        sharing = SimpleNamespace(
            data=lambda project: {"project": project, "items": []},
            save=fail,
        )
        handled = self._routes(sharing=sharing).handle_post(
            handler, "/api/shares", {"project": ["Demo"]}
        )

        self.assertTrue(handled)
        self.assertEqual(400, handler.responses[0][0])
        self.assertEqual("share failed", handler.responses[0][1]["error"])

    def test_unknown_route_is_left_for_next_dispatcher(self):
        routes = self._routes()
        self.assertFalse(routes.handle_get(_Handler(), "/api/reviews", {}))
        self.assertFalse(routes.handle_post(_Handler(), "/api/context", {}))


if __name__ == "__main__":
    unittest.main()
