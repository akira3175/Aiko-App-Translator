"""Durable, optimistic review sessions; proposals never replace a live chapter."""

import difflib
import json
import re
import uuid
from pathlib import Path

from cores.pronouns.storage import _write_lock
from cores.storage.project import _atomic_text, save_json


class ReviewConflict(ValueError):
    pass


def review_path(target):
    target = Path(target)
    return target.parent / ".polish-review" / (target.name + ".json")


def review_blocks(original, proposed):
    def paragraphs(text):
        return [part for part in re.findall(r".*?(?:\n[ \t]*\n+|\Z)", text, re.S) if part]

    old, new = paragraphs(original), paragraphs(proposed)
    blocks = []
    for tag, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and b - a == d - c):
            blocks.extend({"old": left, "new": right} for left, right in zip(old[a:b], new[c:d]))
        else:
            blocks.append({"old": "".join(old[a:b]), "new": "".join(new[c:d])})
    return blocks


def load_review(target):
    path = review_path(target)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def reviewed_text(review, values):
    parts = []
    for block, value in zip(review["blocks"], values):
        # Paragraph boundaries are structural, even when Select All replaces
        # the entire textarea. An empty replacement still means deletion.
        if value and value not in (block["old"], block["new"]):
            suffix = re.search(r"\n[ \t\n]*$", block["new"] or block["old"])
            if suffix and not value.endswith(suffix.group()):
                value = value.rstrip("\n") + suffix.group()
        parts.append(value)
    return "".join(parts)


def create_review(target, original, proposed):
    path = review_path(target)
    with _write_lock(path):
        if path.exists():
            raise ReviewConflict("Chương này còn bản hiệu đính chờ duyệt. Hãy lưu hoặc bỏ phiên trước.")
        blocks = review_blocks(original, proposed)
        review = {"id": uuid.uuid4().hex, "revision": 0, "original": original,
                  "proposed": proposed, "blocks": blocks,
                  "values": [block["new"] for block in blocks]}
        save_json(path, review)
        return review


def change_review(target, request):
    if not isinstance(request, dict):
        raise ValueError("Yêu cầu duyệt không hợp lệ")
    path = review_path(target)
    with _write_lock(path):
        review = load_review(target)
        if not review or request.get("id") != review["id"] or request.get("revision") != review["revision"]:
            raise ReviewConflict("Phiên duyệt đã thay đổi ở nơi khác. Hãy mở lại chương để tải bản mới nhất.")
        action = request.get("action")
        if action == "discard":
            with _write_lock(target):
                current = Path(target).read_text(encoding="utf-8")
                path.unlink()
            return {"ok": True, "translated": current}
        if action not in {"draft", "accept"}:
            raise ValueError("Thao tác duyệt không hợp lệ")
        values = request.get("values")
        if "draft_text" in request:
            content = request["draft_text"]
            if not isinstance(content, str):
                raise ValueError("Nội dung hiệu đính không hợp lệ")
        else:
            if not isinstance(values, list) or len(values) != len(review["blocks"]) or not all(isinstance(v, str) for v in values):
                raise ValueError("Các đoạn hiệu đính không hợp lệ")
            content = reviewed_text(review, values)
        if action == "draft":
            review["draft_text"] = content
            if "draft_text" not in request:
                review["values"] = values
            review["revision"] += 1
            save_json(path, review)
            return {"ok": True, "revision": review["revision"]}
        if not content.strip():
            raise ValueError("Bản đang duyệt trống. Hãy kiểm tra lại trước khi lưu.")
        # Use the same lock for regular editor saves and review acceptance.
        with _write_lock(target):
            current = Path(target).read_text(encoding="utf-8")
            if current != review["original"]:
                raise ReviewConflict("Bản dịch đã được sửa sau khi bắt đầu hiệu đính. Bản đang duyệt vẫn được giữ; hãy đối chiếu trước khi lưu.")
            _atomic_text(Path(target), content, backup=True)
            path.unlink()
        return {"ok": True, "translated": content}


def save_translation(target, content):
    with _write_lock(target):
        _atomic_text(Path(target), content)
