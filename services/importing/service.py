"""Bind chapter-import workflow paths to the application library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.importing.chapters import cancel, confirm, create_preview


@dataclass(frozen=True)
class ChapterImportService:
    runtime_root: Path
    library: object

    def preview(self, project_name, source_format, segment_limit, content):
        project = self.library.safe_project(project_name)
        raw_dir, _translated = self.library.project_folders(project_name)
        return create_preview(
            project_name,
            project,
            raw_dir,
            self.runtime_root,
            source_format,
            segment_limit,
            content,
        )

    def confirm(self, project_name, payload):
        project = self.library.safe_project(project_name)
        raw_dir, _translated = self.library.project_folders(project_name)
        return confirm(project_name, project, raw_dir, payload)

    @staticmethod
    def cancel(token):
        return cancel(token)
