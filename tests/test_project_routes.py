import io
import tempfile
import unittest
from pathlib import Path

from server.routes.projects import ProjectRoutes


class _Handler:
    def __init__(self, body=None):
        self.request_body = body or {}
        self.responses = []
        self.headers = {}
        self.rfile = io.BytesIO()

    def body(self):
        return self.request_body

    def json_response(self, payload, status=200):
        self.responses.append((status, payload))

    def download_response(self, body, content_type, filename):
        self.responses.append((200, (body, content_type, filename)))


class ProjectRouteTests(unittest.TestCase):
    def _routes(self, root, **overrides):
        translated = root / "translated"
        translated.mkdir(exist_ok=True)
        values = {
            "root": root,
            "library": root,
            "projects": lambda: [{"name": "Demo"}],
            "chapters": lambda _project: [
                {"name": "v1_c1_s1.md", "translated": True}
            ],
            "project_folders": lambda _project: (root / "raw", translated),
            "safe_project": lambda name: root / name,
            "validate_project_name": lambda name: name,
            "safe_file": lambda folder, name: folder / name,
            "safe_image": lambda _project, name: root / "image" / name,
            "read_text": lambda path: path.read_text(encoding="utf-8"),
            "chapter_images": lambda _project, _text: [],
            "word_count": lambda path: len(path.read_text(encoding="utf-8").split()),
            "export_book": lambda _project, _options: (b"book", "text/plain", "book.txt"),
            "import_preview": lambda *_args: {"token": "preview"},
            "import_confirm": lambda *_args: {"ok": True},
            "import_cancel": lambda _token: {"ok": True},
        }
        values.update(overrides)
        return ProjectRoutes(**values)

    def test_get_projects_and_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = self._routes(Path(directory))
            handler = _Handler()

            self.assertTrue(routes.handle_get(handler, "/api/projects", {}))
            self.assertTrue(
                routes.handle_get(
                    handler, "/api/chapters", {"project": ["Demo"]}
                )
            )

        self.assertEqual("Demo", handler.responses[0][1]["items"][0]["name"])
        self.assertEqual(1, handler.responses[1][1]["translated"])

    def test_post_chapter_saves_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = self._routes(root)
            handler = _Handler({"translated": "xin chào thế giới"})

            handled = routes.handle_post(
                handler,
                "/api/chapter/v1_c1_s1.md",
                {"project": ["Demo"]},
            )

            self.assertTrue(handled)
            self.assertEqual(4, handler.responses[0][1]["words"])
            self.assertEqual(
                "xin chào thế giới",
                (root / "translated" / "v1_c1_s1.md").read_text(encoding="utf-8"),
            )

    def test_unknown_route_is_left_for_next_dispatcher(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = self._routes(Path(directory))
            self.assertFalse(routes.handle_get(_Handler(), "/api/settings", {}))
            self.assertFalse(routes.handle_post(_Handler(), "/api/jobs", {}))


if __name__ == "__main__":
    unittest.main()
