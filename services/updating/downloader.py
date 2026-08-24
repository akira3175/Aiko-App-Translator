"""Download and validate portable update archives."""

import hashlib
import os
import time
import zipfile
from pathlib import PurePosixPath
from urllib.request import Request, urlopen


class DownloadCancelled(Exception):
    """Raised when the user cancels an update download."""


def validate_archive(path, expected_version):
    required = {
        "NovelTranslatorStudio/app.py",
        "NovelTranslatorStudio/VERSION",
        "NovelTranslatorStudio/runtime/python.exe",
        "NovelTranslatorStudio/apply_update.ps1",
    }
    with zipfile.ZipFile(path) as archive:
        names = set()
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            item = PurePosixPath(normalized)
            if (
                item.is_absolute()
                or ".." in item.parts
                or not item.parts
                or item.parts[0] != "NovelTranslatorStudio"
            ):
                raise ValueError("The update archive contains an unsafe path")
            names.add(normalized.rstrip("/"))
        missing = required - names
        if missing:
            raise ValueError(f"The update archive is missing: {', '.join(sorted(missing))}")
        version = archive.read("NovelTranslatorStudio/VERSION").decode("utf-8-sig").strip()
    if version != expected_version:
        raise ValueError(f"The ZIP contains version {version}, expected {expected_version}")


def download(
    release,
    destination,
    current_version,
    opener=urlopen,
    progress=None,
    cancelled=None,
):
    partial = destination.with_suffix(".zip.part")
    partial.unlink(missing_ok=True)
    request = Request(
        release["download_url"],
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": f"NovelTranslatorStudio/{current_version}",
        },
    )
    digest = hashlib.sha256()
    downloaded = 0
    started = time.monotonic()
    try:
        with opener(request, timeout=60) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0") or 0)
            while True:
                if cancelled and cancelled():
                    raise DownloadCancelled("Update download cancelled")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
                downloaded += len(chunk)
                elapsed = max(time.monotonic() - started, 0.001)
                speed = downloaded / elapsed
                if progress:
                    progress(
                        downloaded=downloaded,
                        total=total,
                        speed=speed,
                        eta=(total - downloaded) / speed if total and speed else None,
                    )
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != release["sha256"]:
        partial.unlink(missing_ok=True)
        raise ValueError("Update SHA-256 checksum does not match")
    os.replace(partial, destination)
    return destination
