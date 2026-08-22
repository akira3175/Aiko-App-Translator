import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server.routes.content import ContentRoutes


class _Handler:
    def __init__(self, body=None):
        self.request_body = body or {}
        self.responses = []

    def body(self):
        return self.request_body

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))


class ContentRouteTests(unittest.TestCase):
    def _routes(self, project_path, **overrides):
        values = {
            "reviews": SimpleNamespace(
                payload=lambda project, source: {
                    "sources": ["review-a.json", "review-z.json"],
                    "source": source or "review-a.json",
                    "items": [],
                }
            ),
            "context": SimpleNamespace(
                data=lambda project: {"project": project},
                save=lambda project, _body: {"project": project},
            ),
            "characters": SimpleNamespace(
                data=lambda project: {"project": project},
                save=lambda project, _body: {"project": project},
            ),
            "pronouns": SimpleNamespace(
                data=lambda project: {"project": project},
                save=lambda project, _body: {"project": project},
            ),
            "prepare_manual_prompt": lambda project: {"project": project},
            "translate_selection": lambda text: {"translated": text},
        }
        values.update(overrides)
        return ContentRoutes(**values)

    def test_reviews_choose_first_sorted_source_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "review-z.json").write_text("{}", encoding="utf-8")
            (project / "review-a.json").write_text("{}", encoding="utf-8")
            handler = _Handler()

            handled = self._routes(project).handle_get(
                handler, "/api/reviews", {"project": ["Demo"]}
            )

        self.assertTrue(handled)
        self.assertEqual("review-a.json", handler.responses[0][1]["source"])
        self.assertEqual(
            ["review-a.json", "review-z.json"],
            handler.responses[0][1]["sources"],
        )

    def test_manual_prompt_timeout_keeps_friendly_message(self):
        def timeout(_project):
            raise subprocess.TimeoutExpired("prompt", 30)

        with tempfile.TemporaryDirectory() as directory:
            handler = _Handler()
            handled = self._routes(
                Path(directory), prepare_manual_prompt=timeout
            ).handle_post(
                handler, "/api/manual-prompt", {"project": ["Demo"]}
            )

        self.assertTrue(handled)
        self.assertEqual(400, handler.responses[0][0])
        self.assertEqual(
            "Tạo prompt quá thời gian cho phép",
            handler.responses[0][1]["error"],
        )

    def test_translate_selection_passes_user_text(self):
        received = []
        with tempfile.TemporaryDirectory() as directory:
            handler = _Handler({"text": "原文"})
            routes = self._routes(
                Path(directory),
                translate_selection=lambda text: received.append(text) or {"ok": True},
            )

            self.assertTrue(
                routes.handle_post(handler, "/api/translate-selection", {})
            )

        self.assertEqual(["原文"], received)

    def test_unknown_route_is_left_for_next_dispatcher(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = self._routes(Path(directory))
            self.assertFalse(routes.handle_get(_Handler(), "/api/health", {}))
            self.assertFalse(routes.handle_post(_Handler(), "/api/shares", {}))


if __name__ == "__main__":
    unittest.main()
