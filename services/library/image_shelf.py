"""Project image shelf and Markdown references."""
import hashlib
import io
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from PIL import Image

LOCAL = re.compile(r"[\w.-]+\.(?:png|jpe?g|gif|webp|svg)", re.I)
REMOTE = re.compile(r"!\[[^\]\n]*\]\((https?://[^\s)]+)\)|\[img(?:=[^\]]+)?\](https?://[^\s\[]+)\[/img\]", re.I)


def image_folder(project):
    folder = project / "image"
    if not project.is_dir() or folder.resolve().parent != project.resolve():
        raise ValueError("Thư mục ảnh không hợp lệ")
    return folder


def list_images(project):
    folder = image_folder(project)
    items = {}
    for path in sorted(folder.glob("*")):
        if LOCAL.fullmatch(path.name) and path.is_file() and path.resolve().parent == folder.resolve():
            url = f"/api/image/{quote(path.name)}?project={quote(project.name)}"
            items[url] = dict(name=path.name, url=url, markup=f"![{path.stem}](../image/{path.name})")
    for subdir in ("raw", "translated"):
        for path in sorted((project / subdir).glob("*.md")):
            if path.resolve().parent != (project / subdir).resolve():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in re.findall(r"!\[[^\]\n]*\]\((?:\.\./)?image/([\w.-]+)\)", text):
                item = items.get(f"/api/image/{quote(name)}?project={quote(project.name)}")
                if item is not None:
                    item.setdefault("chapters", set()).add(path.stem)
            for match in REMOTE.finditer(text):
                url = match.group(1) or match.group(2)
                item = items.setdefault(url, dict(name=path.name, url=url, markup=match.group()))
                item.setdefault("chapters", set()).add(path.stem)
    for item in items.values():
        item["chapters"] = sorted(item.get("chapters", ()))
    return list(items.values())


def add_image(project, name, data):
    folder = image_folder(project)
    try:
        with Image.open(io.BytesIO(data)) as image:
            ext = {"JPEG":"jpg", "PNG":"png", "GIF":"gif", "WEBP":"webp"}[image.format]
            image.verify()
    except (OSError, KeyError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("Chọn ảnh JPG, PNG, GIF hoặc WebP hợp lệ") from exc
    stem = re.sub(r"[^\w-]+", "-", Path(name).stem)[:60].strip("-") or "anh"
    filename = f"{stem}-{hashlib.sha256(data).hexdigest()[:12]}.{ext}"
    folder.mkdir(exist_ok=True)
    try:
        with (folder / filename).open("xb") as out:
            out.write(data)
    except FileExistsError:
        pass
    return filename
