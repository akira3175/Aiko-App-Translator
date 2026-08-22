"""Download and validate portable update archives."""

import hashlib
import os
import zipfile
from pathlib import PurePosixPath
from urllib.request import Request, urlopen


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
                raise ValueError("Gói cập nhật chứa đường dẫn không an toàn")
            names.add(normalized.rstrip("/"))
        missing = required - names
        if missing:
            raise ValueError(f"Gói cập nhật thiếu file: {', '.join(sorted(missing))}")
        version = (
            archive.read("NovelTranslatorStudio/VERSION")
            .decode("utf-8-sig")
            .strip()
        )
    if version != expected_version:
        raise ValueError(
            f"Phiên bản trong ZIP là {version}, không phải {expected_version}"
        )


def download(release, destination, current_version, opener=urlopen):
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
    try:
        with opener(request, timeout=60) as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != release["sha256"]:
        partial.unlink(missing_ok=True)
        raise ValueError("Checksum SHA-256 của bản cập nhật không khớp")
    os.replace(partial, destination)
    return destination
