"""Validation and process control for HTTP-triggered background jobs."""

import re
import threading
from dataclasses import dataclass
from http import HTTPStatus


class JobRequestError(ValueError):
    def __init__(self, message, status=HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class JobController:
    pipelines: object
    jobs: dict
    processes: dict
    translation_kinds: set
    canonical_kind: object
    active_translation: object
    safe_project: object
    validate_hako_targets: object
    pipeline_config: object
    project_folders: object
    safe_file: object
    claim_translation: object
    release_translation: object
    runner: object
    translation_stop_file: object
    terminate_process_tree: object
    thread_factory: object = threading.Thread

    def job(self, kind):
        key = self.canonical_kind(kind)
        return self.jobs.get(key, {"status": "idle", "output": ""})

    def active_jobs(self):
        return [
            {"kind": kind, **job}
            for kind, job in self.jobs.items()
            if job.get("status") == "running"
        ]

    def stream_kind(self, kind):
        key = self.canonical_kind(kind)
        if key not in self.pipelines and key != "retranslate":
            raise JobRequestError("Unknown job", HTTPStatus.NOT_FOUND)
        return key

    def start(self, kind, project, request):
        kind = self.canonical_kind(kind)
        if kind not in self.pipelines or not self.pipelines[kind].exists():
            raise JobRequestError("Pipeline không tồn tại", HTTPStatus.NOT_FOUND)
        if self.jobs.get(kind, {}).get("status") == "running":
            raise JobRequestError("Pipeline đang chạy", HTTPStatus.CONFLICT)
        if kind == "review" and self.active_translation():
            raise JobRequestError(
                "Hãy dừng hoặc chờ dịch xong trước khi Review toàn bộ",
                HTTPStatus.CONFLICT,
            )
        if (
            kind in self.translation_kinds
            and self.jobs.get("review", {}).get("status") == "running"
        ):
            raise JobRequestError(
                "Review toàn bộ đang chạy; hãy chờ review hoàn tất trước khi dịch",
                HTTPStatus.CONFLICT,
            )

        project_path = self.safe_project(project)
        if not project_path.is_dir():
            raise JobRequestError(
                f"Không tìm thấy truyện “{project}”. "
                "Hãy tải lại danh sách truyện và chọn lại."
            )
        config = request.get("config", {})
        if not isinstance(config, dict) or any(
            not isinstance(key, str)
            or (
                isinstance(value, (dict, list))
                and not (kind == "hako-edit" and key == "hako_edit_targets")
            )
            for key, value in config.items()
        ):
            raise JobRequestError("Cấu hình tác vụ không hợp lệ")
        config = dict(config)
        if kind == "hako-edit":
            config["hako_edit_targets"] = self.validate_hako_targets(
                config.get("hako_edit_targets")
            )
        if kind == "pipeline":
            config = self.pipeline_config(config)
        self._validate_counts(config)
        if kind == "manual":
            self._validate_manual(project, config)

        claim = None
        if kind in self.translation_kinds:
            try:
                claim = self.claim_translation(kind, project)
            except ValueError as exc:
                raise JobRequestError(str(exc), HTTPStatus.CONFLICT) from None
        try:
            self.thread_factory(
                target=self.runner.run,
                args=(kind, project, config, claim),
                daemon=True,
            ).start()
        except Exception:
            if claim:
                self.release_translation(claim)
            raise
        return {"ok": True}

    def cancel_translation(self, request):
        mode = request.get("mode")
        if mode not in {"immediate", "after_current"}:
            raise JobRequestError("Chế độ dừng không hợp lệ")
        active = self.active_translation()
        if not active:
            raise JobRequestError("Không có tác vụ dịch đang chạy")
        claim_id = str(active.get("claim_id", ""))
        matching = next(
            (
                (key, job)
                for key, job in self.jobs.items()
                if job.get("claim_id") == claim_id
                and job.get("status") == "running"
            ),
            None,
        )
        job = matching[1] if matching else None
        self.translation_stop_file(claim_id).touch()
        if job is not None:
            job["cancel_mode"] = mode
        if mode == "immediate":
            if job is not None:
                job["output"] = "Đang hủy dịch ngay lập tức…"
            process = self.processes.get(matching[0]) if matching else None
            active_pid = int(active.get("pid") or 0)
            if (
                process is None
                or process.poll() is not None
                or process.pid != active_pid
            ):
                raise JobRequestError(
                    "Không xác định được đúng tiến trình dịch; server vẫn được giữ nguyên"
                )
            self.terminate_process_tree(process.pid)
        return {"ok": True, "mode": mode}

    def cancel_job(self, request):
        kind = self.canonical_kind(request.get("kind", ""))
        job = self.jobs.get(kind)
        process = self.processes.get(kind)
        if not job or job.get("status") != "running" or process is None:
            raise JobRequestError("Không có tác vụ này đang chạy")
        self.runner.task_stop_file(kind).touch()
        job["cancel_mode"] = "immediate"
        job["output"] = "Đang dừng tác vụ…"
        if process.poll() is None:
            self.terminate_process_tree(process.pid)
        return {"ok": True, "kind": kind}

    def retranslate(self, project, request):
        engine = self.canonical_kind(request.get("engine", ""))
        chapter = request.get("chapter", "")
        raw, _ = self.project_folders(project)
        self.safe_file(raw, chapter)
        if engine not in {
            "gemini-api",
            "gemini-web",
            "openai-api",
            "chatgpt-web",
            "interactions",
        }:
            raise JobRequestError("Invalid translation engine")
        if self.jobs.get("retranslate", {}).get("status") == "running":
            raise JobRequestError(
                "A chapter is already being retranslated", HTTPStatus.CONFLICT
            )
        claim = self.claim_translation(engine, project)
        try:
            self.thread_factory(
                target=self.runner.retranslate,
                args=(engine, project, chapter, claim),
                daemon=True,
            ).start()
        except Exception:
            self.release_translation(claim)
            raise
        return {"ok": True}

    @staticmethod
    def _validate_counts(config):
        max_chapters = config.get("max_chapters", "")
        if max_chapters not in (None, ""):
            text = str(max_chapters).strip()
            if isinstance(max_chapters, bool) or not re.fullmatch(r"\d+", text):
                raise JobRequestError(
                    "Số chương muốn chạy phải là số nguyên từ 1 trở lên"
                )
            value = int(text)
            if value < 1:
                raise JobRequestError(
                    "Số chương muốn chạy phải là số nguyên từ 1 trở lên"
                )
            config["max_chapters"] = value
        batch_runs = config.get("batch_runs")
        if batch_runs is not None:
            text = str(batch_runs).strip()
            if isinstance(batch_runs, bool) or not re.fullmatch(r"\d+", text):
                raise JobRequestError(
                    "Số lần chạy batch phải là số nguyên từ 0 trở lên"
                )
            config["batch_runs"] = int(text)

    def _validate_manual(self, project, config):
        target = str(config.get("target_chapter", ""))
        result = str(config.get("manual_result", ""))
        raw, translated = self.project_folders(project)
        self.safe_file(raw, target)
        if (translated / target).exists():
            raise JobRequestError(
                "Chương này đã có bản dịch. Hãy tạo lại prompt cho chương kế tiếp."
            )
        if not result.strip() or len(result.encode("utf-8")) > 5 * 1024 * 1024:
            raise JobRequestError(
                "Kết quả dịch thủ công đang trống hoặc vượt quá 5 MB"
            )
