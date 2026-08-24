"""Prepare a verified portable update and launch its installer."""

import os
import shutil
import subprocess

from services.updating.downloader import DownloadCancelled, download


def prepare_download(
    root,
    update_dir,
    asset_name,
    updater_source,
    current_version,
    jobs,
    release_loader,
    archive_validator,
    progress=None,
    cancelled=None,
    opener=None,
):
    if not (root / "runtime" / "python.exe").is_file():
        raise ValueError("Automatic updates are only available in the portable build")
    if not updater_source.is_file():
        raise ValueError("apply_update.ps1 is missing from the application folder")
    if any(job.get("status") == "running" for job in jobs.values()):
        raise ValueError("Stop or wait for all running tasks before updating")
    release = release_loader(True)
    if not release.get("update_available"):
        raise ValueError("No newer version is available")
    if not release.get("download_ready"):
        raise ValueError("The GitHub release is missing the Windows ZIP or SHA-256 digest")

    update_dir.mkdir(parents=True, exist_ok=True)
    destination = update_dir / asset_name
    download_args = {"progress": progress, "cancelled": cancelled}
    if opener is not None:
        download_args["opener"] = opener
    download(release, destination, current_version, **download_args)
    if cancelled and cancelled():
        destination.unlink(missing_ok=True)
        raise DownloadCancelled("Update download cancelled")
    archive_validator(destination, release["latest_version"])
    updater = update_dir / "apply_update.ps1"
    shutil.copy2(updater_source, updater)
    return {"destination": destination, "updater": updater, "version": release["latest_version"]}


def launch(root, prepared):
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(prepared["updater"]), "-ZipPath", str(prepared["destination"]),
        "-AppRoot", str(root), "-ExpectedVersion", prepared["version"],
        "-ServerPid", str(os.getpid()),
    ]
    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NEW_CONSOLE", 0
    )
    subprocess.Popen(command, cwd=str(root), creationflags=creation_flags)
    return {
        "ok": True,
        "version": prepared["version"],
        "message": "The update is ready. Aiko will restart to finish installing it.",
    }


def prepare(root, update_dir, asset_name, updater_source, current_version, jobs, release_loader, archive_validator):
    prepared = prepare_download(
        root, update_dir, asset_name, updater_source, current_version, jobs,
        release_loader, archive_validator,
    )
    return launch(root, prepared)
