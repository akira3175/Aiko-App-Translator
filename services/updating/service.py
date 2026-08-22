"""Application-bound facade for update checking and installation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from services.updating import checker, downloader, installer


@dataclass(frozen=True)
class UpdateService:
    root: Path
    update_dir: Path
    updater_source: Path
    current_version: str
    repository: str
    release_api: str
    asset_name: str
    jobs: dict
    opener: object = urlopen

    @staticmethod
    def version_parts(value):
        return checker.version_parts(value)

    def payload(self, check_remote=False):
        return checker.payload(
            check_remote,
            self.current_version,
            self.repository,
            self.release_api,
            self.asset_name,
            opener=self.opener,
        )

    @staticmethod
    def validate_archive(path, expected_version):
        return downloader.validate_archive(path, expected_version)

    def prepare(self):
        return installer.prepare(
            self.root,
            self.update_dir,
            self.asset_name,
            self.updater_source,
            self.current_version,
            self.jobs,
            self.payload,
            self.validate_archive,
        )
