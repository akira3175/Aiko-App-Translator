import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.routes.projects import ProjectRoutes
from services.importing.chapters import create_preview, cancel
from services.polish_review import create_review, load_review


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
    def test_large_upload_streams_through_create_and_preview(self):
        size = 301 * 1024 * 1024 + 7

        class Stream:
            remaining = size

            def read(stream, count):
                self.assertLessEqual(count, 1024 * 1024)
                count = min(count, stream.remaining)
                stream.remaining -= count
                return b'x' * count

        def split(source, _volume, _base, *, project_dir, **_kwargs):
            self.assertEqual(Path(source).stat().st_size, size)
            raw = Path(project_dir) / 'raw'
            raw.mkdir()
            (raw / 'v0_c0_s1.md').write_text('# Chapter\n\nContent', encoding='utf-8')
            return {'chapters': 1, 'segments': 1, 'metrics': ['words']}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def preview(project, fmt, limit, content):
                return create_preview(project, root / project, root / project / 'raw',
                                      root / '.runtime', fmt, limit, content, splitter=split)

            routes = self._routes(root, import_preview=preview)
            for endpoint in ('/api/projects', '/api/chapters/import-preview'):
                with self.subTest(endpoint=endpoint):
                    handler = _Handler()
                    handler.headers = {'Content-Length': str(size)}
                    handler.rfile = Stream()
                    with patch('split.chapter_splitter_novelpia_md.split_epub_to_md', side_effect=split):
                        routes.handle_post(handler, endpoint, {'name': ['Demo'], 'project': ['Demo']})
                    status, result = handler.responses[-1]
                    self.assertIn(status, (200, 201), result)
                    self.assertEqual(handler.rfile.remaining, 0)
                    if 'token' in result:
                        cancel(result['token'])
            self.assertFalse((root / 'Demo' / '.import.epub').exists())

    def test_interrupted_upload_cleans_project_and_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def preview(project, fmt, limit, content):
                return create_preview(project, root / project, root / project / 'raw',
                                      root / '.runtime', fmt, limit, content)

            routes = self._routes(root, import_preview=preview)
            for endpoint in ('/api/projects', '/api/chapters/import-preview'):
                handler = _Handler()
                handler.headers = {'Content-Length': '100'}
                handler.rfile = io.BytesIO(b'incomplete')
                routes.handle_post(handler, endpoint, {'name': ['Demo'], 'project': ['Demo']})
                self.assertEqual(handler.responses[-1][0], 400)
                self.assertFalse((root / 'Demo').exists())
                self.assertEqual(list((root / '.runtime' / 'chapter-imports').glob('*')), [])

    def test_rejects_empty_or_invalid_upload_length(self):
        for length in ('0', '-1', 'invalid'):
            handler = _Handler()
            handler.headers = {'Content-Length': length}
            with self.subTest(length=length), self.assertRaises(ValueError):
                ProjectRoutes._upload_body(handler)

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

    def test_chapter_exposes_review_and_accept_endpoint_saves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = self._routes(root)
            name = "v1_c1_s1.md"
            target = root / "translated" / name
            target.write_text("# Cũ\n", encoding="utf-8")
            review = create_review(target, "# Cũ\n", "# Mới\n")
            handler = _Handler()
            routes.handle_get(handler, "/api/chapter/" + name, {"project": ["Demo"]})
            self.assertEqual(review, handler.responses[-1][1]["polish_review"])
            self.assertEqual("# Cũ\n", handler.responses[-1][1]["translated"])
            handler = _Handler({"id": review["id"], "revision": 0, "action": "accept", "values": review["values"]})
            self.assertTrue(routes.handle_post(handler, "/api/polish-review/" + name, {"project": ["Demo"]}))
            self.assertEqual(200, handler.responses[-1][0])
            self.assertEqual("# Mới\n", target.read_text(encoding="utf-8"))
            self.assertIsNone(load_review(target))

    def test_review_endpoint_returns_conflict_for_stale_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = self._routes(root)
            target = root / "translated" / "v1_c1_s1.md"
            target.write_text("Cũ", encoding="utf-8")
            create_review(target, "Cũ", "Mới")
            handler = _Handler({"id": "stale", "revision": 0, "action": "discard"})
            routes.handle_post(handler, "/api/polish-review/v1_c1_s1.md", {"project": ["Demo"]})
            self.assertEqual(409, handler.responses[-1][0])
            self.assertIsNotNone(load_review(target))


if __name__ == "__main__":
    unittest.main()
