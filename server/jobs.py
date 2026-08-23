"""Shared state and process controls for background application jobs."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSLATION_KINDS = {"pipeline", "interactions", "manual", "polish"}
TRANSLATION_LOCK = ROOT / ".runtime" / "translation.lock"
STREAM_PROGRESS_PREFIXES = ("✍️ Đang nhận:", "📥 Đang nhận:")

jobs: dict[str, dict] = {}
job_processes: dict[str, subprocess.Popen] = {}
job_stream_events: dict[str, list[dict]] = {}
translation_guard = threading.RLock()


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def active_translation():
    with translation_guard:
        if not TRANSLATION_LOCK.exists():
            return None
        try:
            data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or data.get("controller_pid") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            data, pid = {}, 0
        if process_is_running(pid):
            return data
        TRANSLATION_LOCK.unlink(missing_ok=True)
        return None


def claim_translation(kind: str, project_name: str):
    with translation_guard:
        active = active_translation()
        if active:
            engine = str(active.get("kind", "engine khác")).upper()
            project = str(active.get("project", "truyện khác"))
            raise ValueError(
                f"{engine} đang chạy cho {project}. Hãy chờ tác vụ kết thúc."
            )
        claim_id = f"{os.getpid()}-{time.time_ns()}"
        TRANSLATION_LOCK.parent.mkdir(exist_ok=True)
        stop_file = translation_stop_file(claim_id)
        stop_file.unlink(missing_ok=True)
        TRANSLATION_LOCK.write_text(
            json.dumps(
                {
                    "claim_id": claim_id,
                    "kind": kind,
                    "project": project_name,
                    "controller_pid": os.getpid(),
                    "pid": None,
                    "stop_file": str(stop_file),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return claim_id


def update_translation_pid(claim_id: str, pid: int):
    with translation_guard:
        data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
        if data.get("claim_id") == claim_id:
            data["pid"] = pid
            TRANSLATION_LOCK.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )


def release_translation(claim_id: str):
    with translation_guard:
        try:
            data = json.loads(TRANSLATION_LOCK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if data.get("claim_id") == claim_id:
            stop_file = Path(str(data.get("stop_file", "")))
            if stop_file.name:
                stop_file.unlink(missing_ok=True)
            TRANSLATION_LOCK.unlink(missing_ok=True)


def translation_stop_file(claim_id: str) -> Path:
    return TRANSLATION_LOCK.parent / f"{claim_id}.stop"


def terminate_process_tree(pid: int):
    if pid <= 0 or pid in {os.getpid(), os.getppid()}:
        raise ValueError("Từ chối dừng tiến trình điều khiển ứng dụng")
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.kill(pid, 15)


def isolated_process_kwargs():
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def merge_process_output(output: str, line: str) -> str:
    """Replace the latest live counter instead of adding one console line per tick."""
    current = line.rstrip("\r\n")
    if current.startswith(STREAM_PROGRESS_PREFIXES):
        lines = output.rstrip("\r\n").splitlines()
        if lines and lines[-1].startswith(STREAM_PROGRESS_PREFIXES):
            lines[-1] = current
        else:
            lines.append(current)
        return ("\n".join(lines) + "\n")[-12000:]
    return (output + line)[-12000:]


def stream_process_output(process: subprocess.Popen, job_key: str) -> str:
    """Publish child-process output to the web console as each line arrives."""
    output = ""
    if process.stdout is not None:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            if line.startswith("@@NOVEL_STREAM@@"):
                try:
                    event = json.loads(line[len("@@NOVEL_STREAM@@") :])
                    current = jobs.get(job_key)
                    if current is not None and isinstance(event, dict):
                        sequence = int(current.get("stream_sequence", 0)) + 1
                        current["stream_sequence"] = sequence
                        event["sequence"] = sequence
                        live_events = job_stream_events.setdefault(job_key, [])
                        live_events.append(dict(event))
                        del live_events[:-1000]
                        events = current.setdefault("stream_events", [])
                        if (
                            events
                            and event.get("type") == "translation_snapshot"
                            and events[-1].get("type") == "translation_snapshot"
                            and events[-1].get("chapter") == event.get("chapter")
                        ):
                            events[-1] = event
                        else:
                            events.append(event)
                            del events[:-300]
                    continue
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass
            output = merge_process_output(output, line)
            current = jobs.get(job_key)
            if current is not None:
                current["output"] = output.rstrip()
        process.stdout.close()
    process.wait()
    return output.strip()
