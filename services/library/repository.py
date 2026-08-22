"""Safe access to novel projects, chapters, images, and text metrics."""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import quote

from cores.storage.project import migrate_project


def safe_project(library: Path, name: str) -> Path:
    if (
        not name
        or name in {"raw", "translated"}
        or not re.fullmatch(r"[\w .-]+", name, re.UNICODE)
    ):
        raise ValueError(
            "Tên truyện không hợp lệ; chỉ dùng chữ, số, khoảng trắng, "
            "dấu chấm, gạch ngang hoặc gạch dưới"
        )
    path = (library / name).resolve()
    if library.resolve() not in path.parents:
        raise ValueError("Invalid project path")
    if path.is_dir():
        migrate_project(path)
    return path


def projects(library: Path):
    library.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            path.name
            for path in library.iterdir()
            if path.is_dir()
            and path.name not in {"raw", "translated"}
            and ((path / "raw").is_dir() or (path / "translated").is_dir())
        ],
        key=str.casefold,
    )


def validate_new_project_name(library: Path, name: str, max_length=60) -> str:
    name = str(name).strip()
    if len(name) > max_length:
        raise ValueError(f"Tên truyện quá dài; tối đa {max_length} ký tự")
    if name.endswith((" ", ".")):
        raise ValueError("Tên truyện không được kết thúc bằng khoảng trắng hoặc dấu chấm")
    stem = name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(
        r"(?:COM|LPT)[1-9]", stem
    ):
        raise ValueError("Tên truyện trùng với tên hệ thống của Windows")
    safe_project(library, name)
    if any(existing.casefold() == name.casefold() for existing in projects(library)):
        raise ValueError(f"Truyện “{name}” đã tồn tại")
    return name


def project_folders(library: Path, name: str):
    project = safe_project(library, name)
    return project / "raw", project / "translated"


def safe_file(folder: Path, name: str) -> Path:
    if not re.fullmatch(r"[\w.-]+\.md", name, re.UNICODE):
        raise ValueError("Tên chương không hợp lệ")
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents:
        raise ValueError("Đường dẫn không hợp lệ")
    return path


def safe_image(library: Path, project_name: str, name: str) -> Path:
    if not re.fullmatch(
        r"[\w.-]+\.(?:jpg|jpeg|png|gif|webp|svg)", name, re.IGNORECASE
    ):
        raise ValueError("Invalid image name")
    folder = safe_project(library, project_name) / "image"
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents:
        raise ValueError("Invalid image path")
    return path


def chapter_images(library: Path, project_name: str, text: str):
    names = re.findall(r"!\[[^\]]*\]\((?:\.\./)?image/([\w.-]+)\)", text)
    local = [
        {
            "id": Path(name).stem,
            "url": f"/api/image/{quote(name)}?project={quote(project_name)}",
        }
        for name in names
        if safe_image(library, project_name, name).exists()
    ]
    remote = [
        {"id": f"remote-{index + 1}", "url": url}
        for index, url in enumerate(
            re.findall(
                r"\[img(?:=[^\]]+)?\](https?://[^\[]+)\[/img\]",
                text,
                re.IGNORECASE,
            )
        )
    ]
    return local + remote


def read_live_utf8(path: Path) -> str:
    """Read a file that another translation process may currently be rewriting."""
    data = b""
    for attempt in range(4):
        data = path.read_bytes()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            if attempt < 3:
                time.sleep(0.05)
    return data.decode("utf-8", errors="replace")


def clean_metric_text(text: str) -> str:
    clean = re.sub(r"\[img\][\s\S]*?\[/img\]", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"^[#>\-+*]+\s*", " ", clean, flags=re.MULTILINE)
    return re.sub(r"[*_~`]+", " ", clean)


def cjk_character_ratio(text: str) -> float:
    clean = re.sub(r"\s+", "", clean_metric_text(text))
    if not clean:
        return 0.0
    cjk = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", clean)
    return len(cjk) / len(clean)


def text_metric(path: Path, character_based=None) -> dict:
    try:
        text = read_live_utf8(path)
    except OSError:
        return {"count": 0, "unit": "từ"}
    clean = clean_metric_text(text)
    if character_based is None:
        character_based = cjk_character_ratio(clean) > 0.5
    if character_based:
        return {"count": sum(character.isalnum() for character in clean), "unit": "ký tự"}
    return {
        "count": len(re.findall(r"[^\W_]+", clean, flags=re.UNICODE)),
        "unit": "từ",
    }


def word_count(path: Path) -> int:
    return text_metric(path)["count"]


def chapter_title(path: Path) -> str:
    try:
        for line in read_live_utf8(path).splitlines():
            title = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
            if title:
                return title
    except OSError:
        pass
    return path.stem


def chapter_key(name: str):
    numbers = re.findall(r"\d+", name)
    return tuple(map(int, numbers)) if numbers else (10**9, name)


def chapters(library: Path, project_name: str):
    raw, translated = project_folders(library, project_name)
    raw.mkdir(parents=True, exist_ok=True)
    translated.mkdir(parents=True, exist_ok=True)
    names = sorted(
        {path.name for path in raw.glob("*.md")}
        | {path.name for path in translated.glob("*.md")},
        key=chapter_key,
    )
    project_text = "\n".join(
        read_live_utf8(raw / name) for name in names if (raw / name).exists()
    )
    character_based = cjk_character_ratio(project_text) > 0.5
    items = []
    for name in names:
        title_path = translated / name if (translated / name).exists() else raw / name
        metric_path = raw / name if (raw / name).exists() else translated / name
        metric = text_metric(metric_path, character_based=character_based)
        items.append(
            {
                "name": name,
                "id": Path(name).stem,
                "title": chapter_title(title_path),
                "raw": (raw / name).exists(),
                "translated": (translated / name).exists(),
                "words": metric["count"],
                "word_unit": metric["unit"],
            }
        )
    return items
