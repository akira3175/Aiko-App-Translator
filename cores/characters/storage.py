"""File persistence for character profiles and progress."""

import os

from cores.storage.project import load_context, load_json, save_json


def load_glossary(context_path: str) -> str:
    return load_context(os.path.dirname(context_path)).get("glossary", "").strip()


def load_markdown(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def save_markdown(content: str, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"Đã lưu: {path}")


def load_index(path: str) -> int:
    return load_json(path, {}).get("char_index", 0)


def save_index(index: int, path: str):
    data = load_json(path, {"schema_version": 1})
    data["char_index"] = index
    save_json(path, data, backup=True)


def build_document(body: str) -> str:
    header = (
        "# Hồ Sơ Nhân Vật\n\n"
        "> File này được tạo tự động. Bạn có thể chỉnh trực tiếp; "
        "ứng dụng sẽ giữ và bổ sung dữ liệu khi chạy lại.\n\n---\n\n"
    )
    return header + body


def document_body(md_text: str) -> str:
    marker = md_text.find("\n## ")
    return md_text[marker:].strip() if marker >= 0 else ""
