"""Library repository bound to one application library directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.library import repository


@dataclass(frozen=True)
class LibraryService:
    root: Path
    max_project_name_length: int = 60

    def safe_project(self, name: str):
        return repository.safe_project(self.root, name)

    def validate_new_project_name(self, name: str):
        return repository.validate_new_project_name(
            self.root, name, max_length=self.max_project_name_length
        )

    def project_folders(self, name: str):
        return repository.project_folders(self.root, name)

    def projects(self):
        return repository.projects(self.root)

    @staticmethod
    def safe_file(folder: Path, name: str):
        return repository.safe_file(folder, name)

    def safe_image(self, project_name: str, name: str):
        return repository.safe_image(self.root, project_name, name)

    def chapter_images(self, project_name: str, text: str):
        return repository.chapter_images(self.root, project_name, text)

    def chapters(self, project_name: str):
        return repository.chapters(self.root, project_name)

    @staticmethod
    def chapter_title(path: Path):
        return repository.chapter_title(path)

    @staticmethod
    def chapter_key(name: str):
        return repository.chapter_key(name)

    @staticmethod
    def read_text(path: Path):
        return repository.read_live_utf8(path)

    @staticmethod
    def clean_metric_text(text: str):
        return repository.clean_metric_text(text)

    @staticmethod
    def cjk_character_ratio(text: str):
        return repository.cjk_character_ratio(text)

    @staticmethod
    def text_metric(path: Path, character_based=None):
        return repository.text_metric(path, character_based=character_based)

    @staticmethod
    def word_count(path: Path):
        return repository.word_count(path)
