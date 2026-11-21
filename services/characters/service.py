"""Read, safely update, restore, and preview structured project character profiles."""

import os
from pathlib import Path

from cores.chapters.files import load_md_chapter, scan_md_dir
from cores.characters.store import (
    FIELDS,
    empty_document,
    JSON_NAME,
    LEGACY_BACKUP_NAME,
    MAX_DOCUMENT_BYTES,
    MD_NAME,
    load_document,
    normalize_chapter,
    parse_legacy_markdown,
    project_paths,
    render_markdown,
    render_snapshot,
    restore_backup,
    save_document,
    validate_document,
)


class CharacterService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

    def _chapters(self, project_dir: Path):
        raw_dir = project_dir / "raw"
        return [os.path.basename(path) for path in scan_md_dir(str(raw_dir))]

    def _payload(self, project_dir: Path, document: dict):
        json_path, md_path, legacy_path = project_paths(project_dir)
        backup_path = json_path.with_name(json_path.name + ".bak")
        return {
            "schema_version": document["schema_version"],
            "revision": document["revision"],
            "characters": document["characters"],
            "fields": [{"key": key, "label": label} for key, label in FIELDS],
            "chapters": self._chapters(project_dir),
            "content": render_markdown(document),
            "exists": json_path.exists() or md_path.exists(),
            "count": len(document["characters"]),
            "backup": backup_path.exists(),
            "legacy_backup": legacy_path.exists(),
            "updated_at": json_path.stat().st_mtime
            if json_path.exists()
            else (md_path.stat().st_mtime if md_path.exists() else None),
            "source_file": JSON_NAME,
            "export_file": MD_NAME,
            "legacy_file": LEGACY_BACKUP_NAME,
        }

    def data(self, project_name):
        project_dir = Path(self._safe_project(project_name))
        try:
            document = load_document(project_dir, migrate=True)
        except (UnicodeError, ValueError):
            if not (project_dir / JSON_NAME).exists() or not (project_dir / (JSON_NAME + ".bak")).exists():
                raise
            return {**self._payload(project_dir, empty_document()), "recovery_required": True}
        return self._payload(project_dir, document)

    def save(self, project_name, payload):
        project_dir = Path(self._safe_project(project_name))
        if not isinstance(payload, dict):
            raise ValueError("Dữ liệu hồ sơ nhân vật không hợp lệ")

        action = str(payload.get("action") or "").strip().lower()
        if action == "restore_backup":
            document = restore_backup(project_dir)
            return self._payload(project_dir, document)

        if "characters" in payload:
            document = save_document(
                project_dir,
                {"characters": payload.get("characters", [])},
                expected_revision=payload.get("expected_revision"),
                allow_empty=bool(payload.get("allow_empty", False)),
            )
            return self._payload(project_dir, document)

        # Backwards-compatible Markdown payload path (e.g. legacy callers/tests).
        content = str(payload.get("content", "")).replace("\r\n", "\n")
        if "\x00" in content or len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("Hồ sơ nhân vật không hợp lệ hoặc vượt quá 5 MB")
        json_path, md_path, _legacy = project_paths(project_dir)
        has_existing = (
            (json_path.exists() and json_path.stat().st_size > 0)
            or (md_path.exists() and md_path.stat().st_size > 0)
        )
        if has_existing and not content.strip():
            raise ValueError("Không thể vô tình xóa sạch hồ sơ nhân vật")
        parsed = parse_legacy_markdown(content)
        document = save_document(
            project_dir,
            parsed,
            expected_revision=payload.get("expected_revision"),
            allow_empty=not has_existing,
        )
        return self._payload(project_dir, document)

    def preview_snapshot(self, project_name, payload):
        """Render the exact Markdown snapshot AI will receive for a chosen chapter."""
        project_dir = Path(self._safe_project(project_name))
        body = payload if isinstance(payload, dict) else {}
        if "characters" in body:
            document = validate_document({"characters": body.get("characters", [])})
        else:
            document = load_document(project_dir, migrate=False)

        raw_chapter = str(body.get("chapter") or "").strip()
        chapter = normalize_chapter(raw_chapter) if raw_chapter else None
        filter_by_text = body.get("filter_by_chapter_text", True)
        if isinstance(filter_by_text, str):
            filter_by_text = filter_by_text.lower() not in {"0", "false", "no", "off"}
        try:
            max_characters = max(1, min(int(body.get("max_characters") or 20), 100))
        except (TypeError, ValueError):
            max_characters = 20

        relevant_text = None
        chapter_found = False
        if chapter and filter_by_text:
            chapter_path = project_dir / "raw" / chapter
            if chapter_path.exists():
                chapter_found = True
                loaded = load_md_chapter(str(chapter_path))
                relevant_text = "\n".join(
                    [loaded.get("title", ""), loaded.get("content", "")]
                )

        markdown = render_snapshot(
            document,
            chapter_id=chapter,
            relevant_text=relevant_text,
            max_characters=max_characters,
        )
        matched_count = markdown.count("\n## ") if markdown else 0
        return {
            "chapter": chapter,
            "markdown": markdown,
            "matched_count": matched_count,
            "total_count": len(document["characters"]),
            "filtered_by_chapter_text": bool(chapter and filter_by_text and chapter_found),
            "chapter_found": chapter_found,
        }
