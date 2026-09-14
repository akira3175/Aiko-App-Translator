"""Keep image positions through translation without relying on paragraph counts."""

import re
from pathlib import Path


IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)")
MARKER_RE = re.compile(r"\[\[IMAGE_[^\]\r\n]*\]\]")
IMAGE_INSTRUCTION = (
    "Giữ nguyên từng mã [[IMAGE_001]], [[IMAGE_002]]... đúng một lần, đúng thứ tự "
    "và đúng vị trí giữa các ý trong nội dung bản dịch. Không dịch, đổi tên, bỏ, "
    "lặp mã hoặc chuyển mã sang tiêu đề. Có thể gộp/tách đoạn nhưng không đưa "
    "nội dung vượt qua vị trí mã ảnh."
)


def mark_images(content):
    if MARKER_RE.search(content):
        raise ValueError("Nội dung đã chứa mã IMAGE; hãy kiểm tra trước khi dịch.")
    images = {}

    def replace(match):
        marker = f"[[IMAGE_{len(images) + 1:03d}]]"
        images[marker] = match.group(0)
        return marker

    return IMAGE_RE.sub(replace, content), images


def validate_image_markers(content, images, title=""):
    if MARKER_RE.findall(content) != list(images) or MARKER_RE.search(title):
        raise ValueError(
            "Mã ảnh bị thiếu, lặp, đổi tên hoặc sai thứ tự. "
            "Bản dịch chưa được lưu; hãy thử lại và giữ nguyên các mã ảnh."
        )
    if IMAGE_RE.search(content):
        raise ValueError("AI đã thêm ảnh ngoài mã ảnh. Bản dịch chưa được lưu; hãy thử lại.")


def restore_images(content, images, title=""):
    validate_image_markers(content, images, title)
    return MARKER_RE.sub(lambda match: images[match.group(0)], content)


def image_mode_path(path):
    return Path(str(path) + ".image-mode")


def uses_image_markers(path):
    metadata = image_mode_path(path)
    return metadata.is_file() and metadata.read_text(encoding="utf-8").strip() == "markers"
