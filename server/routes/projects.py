"""Project, chapter, image, import, and export HTTP routes."""

import json
import mimetypes
import shutil
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import unquote


@dataclass(frozen=True)
class ProjectRoutes:
    root: object
    library: object
    projects: object
    chapters: object
    project_folders: object
    safe_project: object
    validate_project_name: object
    safe_file: object
    safe_image: object
    read_text: object
    chapter_images: object
    word_count: object
    export_book: object
    import_preview: object
    import_confirm: object
    import_cancel: object

    def handle_get(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/projects":
            handler.json_response({"items": self.projects()})
            return True
        if path == "/api/chapters":
            try:
                items = self.chapters(project)
                handler.json_response(
                    {
                        "items": items,
                        "total": len(items),
                        "translated": sum(item["translated"] for item in items),
                    }
                )
            except ValueError as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path.startswith("/api/chapter/"):
            name = unquote(path.rsplit("/", 1)[-1])
            try:
                raw, translated = self.project_folders(project)
                raw_path = self.safe_file(raw, name)
                translated_path = self.safe_file(translated, name)
                raw_text = self.read_text(raw_path) if raw_path.exists() else ""
                handler.json_response(
                    {
                        "name": name,
                        "raw": raw_text,
                        "translated": self.read_text(translated_path)
                        if translated_path.exists()
                        else "",
                        "images": self.chapter_images(project, raw_text),
                    }
                )
            except (ValueError, OSError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path.startswith("/api/image/"):
            try:
                target = self.safe_image(project, unquote(path.rsplit("/", 1)[-1]))
                if not target.is_file():
                    raise ValueError("Image not found")
                data = target.read_bytes()
                handler.send_response(HTTPStatus.OK)
                handler.send_header(
                    "Content-Type",
                    mimetypes.guess_type(target.name)[0]
                    or "application/octet-stream",
                )
                handler.send_header("Content-Length", str(len(data)))
                handler.send_header("Cache-Control", "private, max-age=3600")
                handler.end_headers()
                handler.wfile.write(data)
            except (ValueError, OSError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return True
        return False

    def handle_post(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/export-book":
            try:
                body, content_type, filename = self.export_book(project, handler.body())
                handler.download_response(body, content_type, filename)
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/chapters/import-preview":
            try:
                source_format = query.get("format", ["epub"])[0].lower()
                segment_limit = int(query.get("segment_limit", ["5000"])[0])
                content = self._upload_body(handler)
                handler.json_response(
                    self.import_preview(
                        project, source_format, segment_limit, content
                    )
                )
            except Exception as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/chapters/import-confirm":
            try:
                handler.json_response(self.import_confirm(project, handler.body()))
            except Exception as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/chapters/import-cancel":
            request = handler.body()
            handler.json_response(self.import_cancel(request.get("token", "")))
            return True
        if path == "/api/projects":
            self._create_project(handler, query)
            return True
        if path.startswith("/api/chapter/"):
            name = unquote(path.rsplit("/", 1)[-1])
            try:
                _, translated = self.project_folders(project)
                target = self.safe_file(translated, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    str(handler.body().get("translated", "")), encoding="utf-8"
                )
                handler.json_response({"ok": True, "words": self.word_count(target)})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        return False

    @staticmethod
    def _upload_body(handler):
        length = int(handler.headers.get("Content-Length", 0))
        if not length or length > 300 * 1024 * 1024:
            raise ValueError("File trống hoặc vượt quá 300 MB")
        return handler.rfile.read(length)

    def _create_project(self, handler, query):
        project_path = None
        created_project = False
        try:
            name = self.validate_project_name(query.get("name", [""])[0])
            volume = int(query.get("volume", ["1"])[0])
            segment_limit = int(query.get("segment_limit", ["5000"])[0])
            source_format = query.get("format", ["epub"])[0].lower()
            project_path = self.safe_project(name)
            if project_path.exists():
                raise ValueError(f"Truyện “{name}” đã tồn tại")
            if volume < 0:
                raise ValueError("Volume không hợp lệ")
            if source_format not in {"epub", "txt"}:
                raise ValueError("Chỉ hỗ trợ file EPUB hoặc TXT")
            if not 500 <= segment_limit <= 50000:
                raise ValueError("Giới hạn segment phải từ 500 đến 50.000")
            content = self._upload_body(handler)
            project_path.mkdir(parents=True)
            created_project = True
            (project_path / "translated").mkdir()
            upload = project_path / f".import.{source_format}"
            upload.write_bytes(content)
            from split.chapter_splitter_novelpia_md import (
                split_epub_to_md,
                split_txt_to_md,
            )

            splitter = split_epub_to_md if source_format == "epub" else split_txt_to_md
            result = splitter(
                str(upload),
                volume,
                str(self.root),
                project_dir=str(project_path),
                segment_limit=segment_limit,
                return_details=True,
            )
            upload.unlink(missing_ok=True)
            if result["segments"] <= 0:
                raise ValueError(
                    f"Không tách được chương nào từ {source_format.upper()}"
                )
            handler.json_response(
                {"ok": True, "project": name, **result}, HTTPStatus.CREATED
            )
        except Exception as exc:
            if created_project and project_path is not None and project_path.exists():
                resolved_project = project_path.resolve()
                if resolved_project.parent == self.library.resolve():
                    shutil.rmtree(resolved_project)
            handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
