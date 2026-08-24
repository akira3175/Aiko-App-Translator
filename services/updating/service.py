"""Application-bound facade for update checking and installation."""

from dataclasses import dataclass, field
from pathlib import Path
import threading
from urllib.request import urlopen

from services.updating import checker, downloader, installer


@dataclass
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
    _lock: object = field(default_factory=threading.RLock, init=False, repr=False)
    _cancel: object = field(default_factory=threading.Event, init=False, repr=False)
    _worker: object = field(default=None, init=False, repr=False)
    _prepared: object = field(default=None, init=False, repr=False)
    _progress: dict = field(default_factory=lambda: {"stage": "idle"}, init=False, repr=False)

    @staticmethod
    def version_parts(value):
        return checker.version_parts(value)

    def payload(self, check_remote=False):
        return checker.payload(
            check_remote, self.current_version, self.repository, self.release_api,
            self.asset_name, opener=self.opener,
        )

    @staticmethod
    def validate_archive(path, expected_version):
        return downloader.validate_archive(path, expected_version)

    def start(self):
        with self._lock:
            if self._worker and self._worker.is_alive():
                return {"ok": True, "message": "The update is already downloading."}
            self._cancel.clear()
            self._prepared = None
            self._progress = {
                "stage": "preparing", "downloaded": 0, "total": 0,
                "speed": 0, "eta": None, "percent": None,
            }
            self._worker = threading.Thread(target=self._run, daemon=True, name="aiko-update-download")
            self._worker.start()
        return {"ok": True, "message": "Update download started."}

    def _run(self):
        try:
            prepared = installer.prepare_download(
                self.root, self.update_dir, self.asset_name, self.updater_source,
                self.current_version, self.jobs, self.payload, self.validate_archive,
                progress=self._on_progress, cancelled=self._cancel.is_set,
                opener=self.opener,
            )
            with self._lock:
                self._prepared = prepared
                self._progress.update({"stage": "ready", "version": prepared["version"], "percent": 100})
        except downloader.DownloadCancelled:
            with self._lock:
                self._progress.update({"stage": "cancelled", "message": "Update download cancelled."})
        except Exception as exc:
            with self._lock:
                self._progress.update({"stage": "error", "error": str(exc)})

    def _on_progress(self, **values):
        total = values.get("total", 0)
        downloaded = values.get("downloaded", 0)
        with self._lock:
            self._progress.update(values)
            self._progress["stage"] = "downloading"
            if total:
                self._progress["percent"] = round(downloaded * 100 / total, 1)
            else:
                self._progress.pop("percent", None)

    def progress(self):
        with self._lock:
            return dict(self._progress)

    def cancel(self):
        with self._lock:
            stage = self._progress.get("stage")
            if stage not in {"preparing", "downloading", "ready"}:
                raise ValueError("There is no update download to cancel")
            self._cancel.set()
            if stage == "ready":
                if self._prepared:
                    self._prepared["destination"].unlink(missing_ok=True)
                self._prepared = None
                self._progress.update({"stage": "cancelled", "message": "Update download cancelled."})
        return {"ok": True, "message": "Cancelling update download."}

    def install(self):
        with self._lock:
            if self._progress.get("stage") != "ready" or not self._prepared:
                raise ValueError("The update has not finished downloading")
            prepared = self._prepared
            self._progress["stage"] = "installing"
        return installer.launch(self.root, prepared)

    def prepare(self):
        """Compatibility entrypoint for older callers."""
        prepared = installer.prepare_download(
            self.root, self.update_dir, self.asset_name, self.updater_source,
            self.current_version, self.jobs, self.payload, self.validate_archive,
            opener=self.opener,
        )
        return installer.launch(self.root, prepared)
