import io
import json
import unittest

from server.job_stream import JobStream


class _Handler:
    def __init__(self, output=None):
        self.status = None
        self.headers = []
        self.wfile = output or io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        return None


class _BrokenOutput:
    def write(self, _data):
        raise BrokenPipeError()

    def flush(self):
        return None


class JobStreamTests(unittest.TestCase):
    def test_sends_only_newer_events_then_done(self):
        events = {
            "pipeline": [
                {"sequence": 1, "text": "old"},
                {"sequence": 2, "text": "mới"},
            ]
        }
        jobs = {"pipeline": {"status": "done"}}
        handler = _Handler()

        JobStream(events, jobs, sleep=lambda _seconds: None).serve(
            handler, "pipeline", 1
        )

        output = handler.wfile.getvalue().decode("utf-8")
        data_line = next(line for line in output.splitlines() if line.startswith("data: "))
        event = json.loads(data_line.removeprefix("data: "))
        self.assertEqual("mới", event["text"])
        self.assertNotIn("old", output)
        self.assertIn("event: done", output)

    def test_sends_ping_after_ten_seconds(self):
        now = [0.0]
        sleeps = [0]
        jobs = {"pipeline": {"status": "running"}}

        def sleep(_seconds):
            sleeps[0] += 1
            now[0] += 11
            if sleeps[0] == 2:
                jobs["pipeline"]["status"] = "done"

        handler = _Handler()
        JobStream({}, jobs, clock=lambda: now[0], sleep=sleep).serve(
            handler, "pipeline", 0
        )

        self.assertIn(b": ping\n\n", handler.wfile.getvalue())
        self.assertIn(b"event: done", handler.wfile.getvalue())

    def test_disconnect_is_ignored(self):
        handler = _Handler(_BrokenOutput())
        stream = JobStream({}, {"pipeline": {"status": "done"}})

        self.assertIsNone(stream.serve(handler, "pipeline", 0))
        self.assertEqual(200, handler.status)


if __name__ == "__main__":
    unittest.main()
