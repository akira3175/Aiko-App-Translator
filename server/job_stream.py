"""Server-Sent Events transport for live background-job updates."""

import json
import time
from http import HTTPStatus


class JobStream:
    def __init__(self, events, jobs, clock=time.monotonic, sleep=time.sleep):
        self.events = events
        self.jobs = jobs
        self.clock = clock
        self.sleep = sleep

    def serve(self, handler, job_key, after):
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        last_sequence = after
        last_ping = self.clock()
        try:
            while True:
                pending = [
                    event
                    for event in self.events.get(job_key, [])
                    if int(event.get("sequence", 0)) > last_sequence
                ]
                for event in pending:
                    payload = json.dumps(event, ensure_ascii=False)
                    handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    last_sequence = int(event.get("sequence", last_sequence))
                if pending:
                    handler.wfile.flush()
                job = self.jobs.get(job_key, {})
                if job.get("status") in {"done", "error", "cancelled"} and not pending:
                    handler.wfile.write(b"event: done\ndata: {}\n\n")
                    handler.wfile.flush()
                    return
                if self.clock() - last_ping >= 10:
                    handler.wfile.write(b": ping\n\n")
                    handler.wfile.flush()
                    last_ping = self.clock()
                self.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
