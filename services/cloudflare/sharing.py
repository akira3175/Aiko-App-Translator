"""Private chapter sharing backed by a Cloudflare R2-compatible client."""

from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from cores.storage.project import load_json, save_json


SEGMENT_RE = re.compile(r"^v(\d+)_c(\d+)_s(\d+)\.md$", re.IGNORECASE)


def chapter_identity(name: str):
    match = re.match(r"^v(\d+)_c(\d+)(?:_s\d+)?\.md$", name, re.IGNORECASE)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _chapter_key(name: str):
    numbers = re.findall(r"\d+", name)
    return tuple(map(int, numbers)) if numbers else (10**9, name)


def chapter_groups(paths):
    groups = {}
    for path in paths:
        match = SEGMENT_RE.match(path.name)
        if match:
            volume, chapter, segment = map(int, match.groups())
            identity = (volume, chapter)
            group = groups.setdefault(
                identity,
                {
                    "identity": identity,
                    "name": f"v{volume}_c{chapter}.md",
                    "paths": [],
                },
            )
            group["paths"].append((segment, path))
        else:
            identity = ("file", path.name.casefold())
            group = groups.setdefault(
                identity,
                {"identity": None, "name": path.name, "paths": []},
            )
            group["paths"].append((0, path))
    result = []
    for group in groups.values():
        group["paths"] = [
            path
            for _segment, path in sorted(
                group["paths"], key=lambda item: (item[0], item[1].name.casefold())
            )
        ]
        result.append(group)
    return sorted(result, key=lambda item: _chapter_key(item["name"]))


def _read_live_utf8(path: Path) -> str:
    data = b""
    for attempt in range(4):
        data = path.read_bytes()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            if attempt < 3:
                time.sleep(0.05)
    return data.decode("utf-8", errors="replace")


def merged_markdown(paths):
    first_lines = _read_live_utf8(paths[0]).splitlines()
    title = next(
        (
            re.sub(r"^\s*#{1,6}\s*", "", line).strip()
            for line in first_lines
            if line.strip() and re.match(r"^\s*#{1,6}\s+", line)
        ),
        paths[0].stem,
    )
    bodies = []
    for path in paths:
        lines = _read_live_utf8(path).splitlines()
        for index, line in enumerate(lines):
            if line.strip():
                if re.match(r"^\s*#{1,6}\s+", line):
                    del lines[index]
                break
        body = "\n".join(lines).strip()
        if body:
            bodies.append(body)
    content = f"# {title}"
    if bodies:
        content += "\n\n" + "\n\n".join(bodies)
    return content, title


def _safe_child(folder: Path, name: str) -> Path:
    path = (folder / name).resolve()
    if path.parent != folder.resolve():
        raise ValueError("Tên tệp không hợp lệ")
    return path


def _store_path(project_path: Path) -> Path:
    return project_path / "sharing.json"


def load_shares(project_path: Path) -> list[dict]:
    path = _store_path(project_path)
    if not path.exists():
        return []
    data = load_json(path, {})
    shares = data.get("shares", []) if isinstance(data, dict) else []
    return shares if isinstance(shares, list) else []


def save_shares(project_path: Path, shares: list[dict]):
    save_json(_store_path(project_path), {"shares": shares}, backup=True)


def shares_data(project_path: Path, worker_url: str, configured: bool) -> dict:
    worker_url = str(worker_url).strip().rstrip("/")
    items = []
    for share in load_shares(project_path):
        item = dict(share)
        token = str(item.pop("token", ""))
        item["url"] = (
            f"{worker_url}/?share={quote(str(item.get('id', '')))}&token={quote(token)}"
            if worker_url and token
            else ""
        )
        items.append(item)
    return {"items": items, "configured": bool(worker_url and configured)}


def _manifest(share: dict) -> dict:
    return {
        "version": 1,
        "id": share["id"],
        "title": share["title"],
        "recipient": share.get("recipient", ""),
        "expires_at": share["expires_at"],
        "token_hash": hashlib.sha256(str(share["token"]).encode("utf-8")).hexdigest(),
        "chapters": share.get("chapters", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _chapter_html(project_path: Path, text: str, share_id: str):
    images, output = [], []
    image_dir = project_path / "image"
    for raw_line in unicodedata.normalize("NFC", text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        local = re.fullmatch(r"!\[([^\]]*)\]\((?:\.\./)?image/([\w.-]+)\)", line)
        remote = re.fullmatch(
            r"\[img(?:=[^\]]+)?\](https?://[^\[]+)\[/img\]", line, re.IGNORECASE
        )
        if local:
            name = local.group(2)
            path = _safe_child(image_dir, name)
            if path.is_file():
                item = {
                    "name": name,
                    "key": f"shares/{share_id}/images/{name}",
                    "content_type": {
                        ".webp": "image/webp",
                        ".avif": "image/avif",
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".gif": "image/gif",
                    }.get(path.suffix.lower())
                    or mimetypes.guess_type(name)[0]
                    or "application/octet-stream",
                }
                images.append((item, path))
                caption = html.escape(local.group(1).strip() or Path(name).stem)
                output.append(
                    f'<figure><img data-share-image="{html.escape(name, quote=True)}" '
                    f'alt="{caption}" loading="lazy"><figcaption>{caption}</figcaption></figure>'
                )
            continue
        if remote:
            url = html.escape(remote.group(1).strip(), quote=True)
            output.append(f'<figure><img src="{url}" alt="" loading="lazy"></figure>')
            continue
        escaped = html.escape(raw_line)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(^|[^*])\*([^*]+?)\*", r"\1<em>\2</em>", escaped)
        if escaped.startswith("### "):
            output.append(f"<h3>{escaped[4:]}</h3>")
        elif escaped.startswith("## "):
            output.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("# "):
            output.append(f"<h1>{escaped[2:]}</h1>")
        else:
            output.append(f"<p>{escaped}</p>")
    return "".join(output), images


def remove_chapter(project_path: Path, share_id: str, chapter_name: str, config, client):
    shares = load_shares(project_path)
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    if share is None:
        raise ValueError("Không tìm thấy bản share")
    chapter = next(
        (item for item in share.get("chapters", []) if str(item.get("name")) == chapter_name),
        None,
    )
    if chapter is None:
        raise ValueError("Chương không nằm trong bản share")
    share["chapters"] = [
        item for item in share.get("chapters", []) if str(item.get("name")) != chapter_name
    ]
    client.put_object(
        Bucket=config["bucket"],
        Key=f"shares/{share_id}/manifest.json",
        Body=json.dumps(_manifest(share), ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="private, no-store",
    )
    remaining_images = {
        str(image.get("key"))
        for item in share["chapters"]
        for image in item.get("images", [])
        if image.get("key")
    }
    keys = [str(chapter["key"])] + [
        str(image.get("key"))
        for image in chapter.get("images", [])
        if image.get("key") and str(image.get("key")) not in remaining_images
    ]
    client.delete_objects(
        Bucket=config["bucket"],
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )
    save_shares(project_path, shares)
    return shares_data(project_path, config.get("worker_url", ""), config.get("bucket"))


def close(project_path: Path, share_id: str, config, client):
    shares = load_shares(project_path)
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    if share is None:
        raise ValueError("Không tìm thấy bản share")
    keys = [str(item.get("key")) for item in share.get("chapters", []) if item.get("key")]
    keys.extend(
        str(image.get("key"))
        for item in share.get("chapters", [])
        for image in item.get("images", [])
        if image.get("key")
    )
    keys.append(f"shares/{share_id}/manifest.json")
    result = client.delete_objects(
        Bucket=config["bucket"],
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )
    if result.get("Errors"):
        raise ValueError("R2 không xóa được toàn bộ dữ liệu của bản share")
    save_shares(
        project_path, [item for item in shares if str(item.get("id")) != share_id]
    )
    return shares_data(project_path, config.get("worker_url", ""), config.get("bucket"))


def save(project_name: str, project_path: Path, payload: dict, config, client):
    action = str(payload.get("action", "")).strip()
    share_id = str(payload.get("share_id", "")).strip()
    if action == "remove_chapter":
        return remove_chapter(
            project_path, share_id, str(payload.get("chapter", "")).strip(), config, client
        )
    if action == "close":
        return close(project_path, share_id, config, client)
    names = payload.get("chapters", [])
    if not isinstance(names, list) or not names:
        raise ValueError("Hãy chọn ít nhất một chương đã dịch")
    paths = [_safe_child(project_path / "translated", str(name)) for name in names]
    if any(not path.is_file() for path in paths):
        raise ValueError("Có chương chưa có bản dịch để chia sẻ")
    shares = load_shares(project_path)
    share = next((item for item in shares if str(item.get("id")) == share_id), None)
    now = datetime.now(timezone.utc)
    if share is None:
        share_id = secrets.token_hex(8)
        share = {
            "id": share_id,
            "token": secrets.token_urlsafe(32),
            "title": str(payload.get("title", project_name)).strip() or project_name,
            "recipient": str(payload.get("recipient", "")).strip(),
            "created_at": now.isoformat(),
            "chapters": [],
        }
        shares.append(share)
    else:
        share["title"] = str(payload.get("title", share.get("title", project_name))).strip() or share.get("title", project_name)
        share["recipient"] = str(payload.get("recipient", share.get("recipient", ""))).strip()
    days = max(1, min(int(payload.get("expires_days", 30)), 3650))
    share["expires_at"] = (now + timedelta(days=days)).isoformat()
    chapter_map = {
        str(item.get("name")): item
        for item in share.get("chapters", [])
        if isinstance(item, dict)
    }
    stale_keys = []
    for group in chapter_groups(paths):
        content, title = merged_markdown(group["paths"])
        output_name = group["name"]
        key = f"shares/{share_id}/chapters/{output_name}"
        chapter_html, local_images = _chapter_html(project_path, content, share_id)
        client.put_object(
            Bucket=config["bucket"], Key=key, Body=chapter_html.encode("utf-8"),
            ContentType="text/html; charset=utf-8", CacheControl="private, no-store",
        )
        for image, image_path in local_images:
            client.put_object(
                Bucket=config["bucket"], Key=image["key"], Body=image_path.read_bytes(),
                ContentType=image["content_type"], CacheControl="private, no-store",
            )
        aliases = [
            name for name in chapter_map
            if name == output_name
            or (group["identity"] is not None and chapter_identity(name) == group["identity"])
        ]
        for alias in aliases:
            previous = chapter_map.pop(alias)
            if previous.get("key") and str(previous["key"]) != key:
                stale_keys.append(str(previous["key"]))
            stale_keys.extend(
                str(image.get("key"))
                for image in previous.get("images", [])
                if image.get("key")
            )
        chapter_map[output_name] = {
            "name": output_name, "title": title, "key": key, "format": "html",
            "images": [image for image, _path in local_images], "updated_at": now.isoformat(),
        }
    share["chapters"] = sorted(
        chapter_map.values(), key=lambda item: _chapter_key(str(item["name"]))
    )
    active_images = {
        str(image.get("key"))
        for item in share["chapters"]
        for image in item.get("images", [])
        if image.get("key")
    }
    stale_keys = [key for key in stale_keys if key not in active_images]
    client.put_object(
        Bucket=config["bucket"], Key=f"shares/{share_id}/manifest.json",
        Body=json.dumps(_manifest(share), ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8", CacheControl="private, no-store",
    )
    if stale_keys:
        client.delete_objects(
            Bucket=config["bucket"],
            Delete={"Objects": [{"Key": key} for key in sorted(set(stale_keys))], "Quiet": True},
        )
    save_shares(project_path, shares)
    return shares_data(project_path, config.get("worker_url", ""), config.get("bucket"))
