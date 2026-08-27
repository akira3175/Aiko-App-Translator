"""Subprocess lifecycle for background translation jobs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobRunner:
    root: Path
    pipelines: dict
    jobs: dict
    processes: dict
    stream_events: dict
    saved_settings: object
    task_options: object
    safe_project: object
    project_folders: object
    safe_file: object
    translation_stop_file: object
    update_translation_pid: object
    release_translation: object
    stream_process_output: object
    process_kwargs: object
    active_translation: object
    popen: object = subprocess.Popen
    run_process: object = subprocess.run

    def task_stop_file(self, kind: str) -> Path:
        safe_kind = re.sub(r"[^a-z0-9_-]", "", kind.lower())
        return self.root / ".runtime" / f"{safe_kind}.stop"

    def prepare_manual_prompt(self, project_name: str):
        project = self.safe_project(project_name)
        if not project.is_dir():
            raise ValueError(f"Không tìm thấy truyện “{project_name}”")
        if self.active_translation():
            raise ValueError("Hãy chờ tác vụ dịch hiện tại kết thúc trước khi tạo prompt")
        cache = project / ".manual_prompt.json"
        cache.unlink(missing_ok=True)
        config = {**self.saved_settings(), "manual_result": "", "skip_login_prompt": True}
        process = self.run_process(
            [sys.executable, "-u", str(self.pipelines["manual"])],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=self._environment(project_name, config),
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or "").strip()[-1500:]
            raise ValueError(detail or "Không thể tạo prompt dịch thủ công")
        if not cache.exists():
            raise ValueError("Không còn chương chưa dịch để tạo prompt")
        data = json.loads(cache.read_text(encoding="utf-8"))
        chapter = str(data.get("chapter", ""))
        prompt = str(data.get("prompt", ""))
        raw, translated = self.project_folders(project_name)
        self.safe_file(raw, chapter)
        if (translated / chapter).exists():
            raise ValueError("Chương vừa chọn đã có bản dịch. Hãy tải lại danh sách chương")
        if not prompt.strip():
            raise ValueError("Prompt dịch thủ công đang trống")
        return {
            "chapter": chapter,
            "title": str(data.get("title", Path(chapter).stem)),
            "prompt": prompt,
        }

    def run(self, kind, project_name, config=None, translation_claim=None):
        self.stream_events[kind] = []
        task_config = dict(config or {})
        if kind == "manual":
            manual_result = str(task_config.pop("manual_result", ""))
            result_path = self.safe_project(project_name) / ".manual_result.txt"
            temporary = result_path.with_name(result_path.name + ".tmp")
            temporary.write_text(manual_result, encoding="utf-8")
            os.replace(temporary, result_path)
            task_config["manual_result_ready"] = True
        effective_config = {
            **self.saved_settings(),
            **task_config,
            **self.task_options(project_name),
        }
        streaming = kind == "interactions" or (
            kind == "pipeline"
            and str(effective_config.get("translate_provider", "")).lower() == "gemini-api"
            and str(effective_config.get("gemini_api_streaming", "off")).lower() == "on"
        )
        script = self.pipelines["interactions"] if streaming else self.pipelines[kind]
        stop_file = self.task_stop_file(kind)
        stop_file.parent.mkdir(exist_ok=True)
        stop_file.unlink(missing_ok=True)
        self.jobs[kind] = self._running_job(
            project_name, translation_claim, streaming, "Đang khởi động…"
        )
        if kind == "polish":
            self.jobs[kind]["chapter"] = str(task_config.get("target_chapter", ""))
        if kind == "review" and task_config.get("workspace_review"):
            self.jobs[kind]["workspace_review"] = True
            self.jobs[kind]["chapter"] = str(task_config.get("target_chapter", ""))
        try:
            process = self._start_process(
                kind,
                script,
                project_name,
                effective_config,
                translation_claim,
                self.translation_stop_file(translation_claim)
                if translation_claim
                else stop_file,
            )
            output = self.stream_process_output(process, kind)
            cancelled = self.jobs.get(kind, {}).get("cancel_mode") == "immediate"
            status = "cancelled" if cancelled else ("done" if process.returncode == 0 else "error")
            self._finish_job(kind, status, output)
        except Exception as exc:
            self._finish_job(kind, "error", str(exc))
        finally:
            self.processes.pop(kind, None)
            stop_file.unlink(missing_ok=True)
            if translation_claim:
                self.release_translation(translation_claim)

    def retranslate(self, engine, project_name, chapter_name, translation_claim):
        job_key = "retranslate"
        self.stream_events[job_key] = []
        _, translated = self.project_folders(project_name)
        target = self.safe_file(translated, chapter_name)
        backup = target.with_suffix(target.suffix + ".web-backup")
        config = {
            **self.saved_settings(),
            **self.task_options(project_name),
            "run_until_complete": False,
            "skip_login_prompt": True,
            "target_chapter": chapter_name,
        }
        engine = str(engine)
        streaming = engine == "interactions" or (
            engine == "gemini-api"
            and str(config.get("gemini_api_streaming", "off")).lower() == "on"
        )
        pipeline_kind = "interactions" if streaming else "pipeline"
        if engine in {"gemini-api", "gemini-web", "google-ai-studio-web", "openai-api", "chatgpt-web"}:
            config["translate_provider"] = engine
        self.jobs[job_key] = self._running_job(
            project_name,
            translation_claim,
            streaming,
            f"Retranslating {chapter_name} with {engine.upper()}...",
        )
        try:
            backup.unlink(missing_ok=True)
            if target.exists():
                target.replace(backup)
            process = self._start_process(
                job_key,
                self.pipelines[pipeline_kind],
                project_name,
                config,
                translation_claim,
                self.translation_stop_file(translation_claim),
            )
            output = self.stream_process_output(process, job_key)
            cancelled = self.jobs.get(job_key, {}).get("cancel_mode") == "immediate"
            if cancelled or process.returncode != 0 or not target.exists():
                if backup.exists():
                    backup.replace(target)
                self._finish_job(
                    job_key,
                    "cancelled" if cancelled else "error",
                    output or "Translation did not create an output file",
                )
                return
            backup.unlink(missing_ok=True)
            self._finish_job(job_key, "done", output)
        except Exception as exc:
            if backup.exists():
                target.unlink(missing_ok=True)
                backup.replace(target)
            self._finish_job(job_key, "error", str(exc))
        finally:
            self.processes.pop(job_key, None)
            self.release_translation(translation_claim)

    def _start_process(self, job_key, script, project, config, claim, stop_file):
        process = self.popen(
            [sys.executable, "-u", str(script)],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._environment(project, config, stop_file),
            **self.process_kwargs(),
        )
        self.processes[job_key] = process
        if claim:
            self.update_translation_pid(claim, process.pid)
        return process

    @staticmethod
    def _running_job(project, claim, streaming, output):
        return {
            "status": "running",
            "output": output,
            "project": project,
            "streaming": streaming,
            "claim_id": claim,
            "stream_events": [],
            "stream_sequence": 0,
        }

    def _finish_job(self, key, status, output):
        state = self.jobs.get(key, {})
        self.jobs[key] = {
            "status": status,
            "output": output,
            "stream_events": state.get("stream_events", []),
            "stream_sequence": state.get("stream_sequence", 0),
        }

    @staticmethod
    def _environment(project, config, stop_file=None):
        environment = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "NOVEL_PROJECT": project,
            "NOVEL_WEB_MODE": "1",
            "NOVEL_WEB_CONFIG": json.dumps(config, ensure_ascii=False),
        }
        if stop_file is not None:
            environment["NOVEL_STOP_FILE"] = str(stop_file)
        return environment
