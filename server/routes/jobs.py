"""HTTP routes for background jobs and translation process control."""

import json
from http import HTTPStatus
from urllib.parse import unquote

from server.job_controller import JobRequestError


class JobRoutes:
    def __init__(self, controller):
        self.controller = controller

    def handle_get(self, handler, path, query):
        if path.startswith("/api/job/"):
            handler.json_response(self.controller.job(path.rsplit("/", 1)[-1]))
            return True
        if path == "/api/jobs/active":
            handler.json_response({"items": self.controller.active_jobs()})
            return True
        if path.startswith("/api/job-stream/"):
            try:
                kind = self.controller.stream_kind(
                    unquote(path.rsplit("/", 1)[-1])
                )
                try:
                    after = max(0, int(query.get("after", ["0"])[0]))
                except ValueError:
                    after = 0
                handler.stream_job_events(kind, after)
            except JobRequestError as exc:
                handler.json_response({"error": str(exc)}, exc.status)
            return True
        return False

    def handle_post(self, handler, path, query):
        project = query.get("project", [""])[0]
        try:
            if path.startswith("/api/run/"):
                result = self.controller.start(
                    path.rsplit("/", 1)[-1], project, handler.body()
                )
                handler.json_response(result, HTTPStatus.ACCEPTED)
                return True
            if path == "/api/translation/cancel":
                handler.json_response(
                    self.controller.cancel_translation(handler.body())
                )
                return True
            if path == "/api/job/cancel":
                handler.json_response(self.controller.cancel_job(handler.body()))
                return True
            if path == "/api/retranslate":
                handler.json_response(
                    self.controller.retranslate(project, handler.body()),
                    HTTPStatus.ACCEPTED,
                )
                return True
        except JobRequestError as exc:
            handler.json_response({"error": str(exc)}, exc.status)
            return True
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        return False
