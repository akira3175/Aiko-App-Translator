import unittest

from server.dispatcher import RouteDispatcher


class _Route:
    def __init__(self, name, calls, handled=False):
        self.name = name
        self.calls = calls
        self.handled = handled

    def handle_get(self, handler, path, query):
        self.calls.append((self.name, "get", handler, path, query))
        return self.handled

    def handle_post(self, handler, path, query):
        self.calls.append((self.name, "post", handler, path, query))
        return self.handled


class RouteDispatcherTests(unittest.TestCase):
    def test_dispatches_in_order_and_stops_after_handled(self):
        calls = []
        handler = object()
        query = {"project": ["Demo"]}
        dispatcher = RouteDispatcher(
            [
                _Route("first", calls),
                _Route("second", calls, handled=True),
                _Route("third", calls, handled=True),
            ]
        )

        handled = dispatcher.handle_get(handler, "/api/context", query)

        self.assertTrue(handled)
        self.assertEqual(["first", "second"], [call[0] for call in calls])
        self.assertIs(handler, calls[0][2])
        self.assertIs(query, calls[0][4])

    def test_skips_route_without_requested_method(self):
        calls = []

        class GetOnly:
            def handle_get(self, *_args):
                return True

        dispatcher = RouteDispatcher(
            [GetOnly(), _Route("post", calls, handled=True)]
        )

        self.assertTrue(dispatcher.handle_post(object(), "/api/settings", {}))
        self.assertEqual(["post"], [call[0] for call in calls])

    def test_returns_false_when_no_route_handles_request(self):
        dispatcher = RouteDispatcher([_Route("route", [], handled=False)])
        self.assertFalse(dispatcher.handle_get(object(), "/api/health", {}))

    def test_does_not_swallow_route_errors(self):
        class BrokenRoute:
            def handle_get(self, *_args):
                raise RuntimeError("route failed")

        with self.assertRaisesRegex(RuntimeError, "route failed"):
            RouteDispatcher([BrokenRoute()]).handle_get(
                object(), "/api/context", {}
            )


if __name__ == "__main__":
    unittest.main()
