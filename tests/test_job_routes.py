import unittest
from types import SimpleNamespace

from server.job_controller import JobRequestError
from server.routes.jobs import JobRoutes


class _Handler:
    def __init__(self, body=None):
        self.request_body = body or {}
        self.responses = []
        self.streams = []

    def body(self):
        return self.request_body

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))

    def stream_job_events(self, kind, after):
        self.streams.append((kind, after))


class JobRouteTests(unittest.TestCase):
    def test_stream_route_passes_sequence_to_handler(self):
        controller = SimpleNamespace(stream_kind=lambda kind: kind)
        routes = JobRoutes(controller)
        handler = _Handler()

        self.assertTrue(
            routes.handle_get(
                handler, "/api/job-stream/pipeline", {"after": ["12"]}
            )
        )
        self.assertEqual([("pipeline", 12)], handler.streams)

    def test_controller_conflict_is_returned_with_original_status(self):
        def conflict(*_args):
            raise JobRequestError("Pipeline đang chạy", 409)

        controller = SimpleNamespace(start=conflict)
        routes = JobRoutes(controller)
        handler = _Handler({"config": {}})

        self.assertTrue(
            routes.handle_post(
                handler, "/api/run/pipeline", {"project": ["Demo"]}
            )
        )
        self.assertEqual(409, handler.responses[0][0])

    def test_unknown_route_is_left_for_next_dispatcher(self):
        routes = JobRoutes(SimpleNamespace())
        self.assertFalse(routes.handle_get(_Handler(), "/api/settings", {}))
        self.assertFalse(routes.handle_post(_Handler(), "/api/shares", {}))


if __name__ == "__main__":
    unittest.main()
