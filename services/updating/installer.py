"""Prepare a verified portable update and launch its installer."""

import os
import shutil
import subprocess

from services.updating.downloader import download


def prepare(
    root,
    update_dir,
    asset_name,
    updater_source,
    current_version,
    jobs,
    release_loader,
    archive_validator,
):
    if not (root / "runtime" / "python.exe").is_file():
        raise ValueError("Tự động cập nhật chỉ dùng được trên bản portable")
    if not updater_source.is_file():
        raise ValueError("Thiếu apply_update.ps1 trong thư mục ứng dụng")
    if any(job.get("status") == "running" for job in jobs.values()):
        raise ValueError("Hãy chờ hoặc dừng mọi tác vụ trước khi cập nhật")
    release = release_loader(True)
    if not release.get("update_available"):
        raise ValueError("Không có phiên bản mới để cập nhật")
    if not release.get("download_ready"):
        raise ValueError("Release GitHub thiếu ZIP Windows hoặc SHA-256")

    update_dir.mkdir(parents=True, exist_ok=True)
    destination = update_dir / asset_name
    download(release, destination, current_version)
    archive_validator(destination, release["latest_version"])
    updater = update_dir / "apply_update.ps1"
    shutil.copy2(updater_source, updater)
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(updater),
        "-ZipPath",
        str(destination),
        "-AppRoot",
        str(root),
        "-ExpectedVersion",
        release["latest_version"],
        "-ServerPid",
        str(os.getpid()),
    ]
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NEW_CONSOLE", 0
    )
    subprocess.Popen(command, cwd=str(root), creationflags=creation_flags)
    return {
        "ok": True,
        "version": release["latest_version"],
        "message": "Đã tải và xác minh. App sẽ khởi động lại để cập nhật.",
    }
