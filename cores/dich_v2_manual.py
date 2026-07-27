"""Dịch thủ công từng chương Markdown qua file hoặc giao diện web."""

import json
import msvcrt
import os
import re
import sys
import time

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cores.dich_utils import (
    CONTEXT_YAML,
    NOVEL_TXT,
    RAW_DIR,
    TRANSLATED_DIR,
    is_translated,
    scan_md_dir,
)
from cores.runtime_config import bool_option, option, web_mode
from cores.translation_prompts import build_single_prompt
from cores.translation_workflows import run_single_translation

MANUAL_PROMPT_FILE = "manual_prompt.txt"
_PROJECT_DIR = os.path.dirname(RAW_DIR)
MANUAL_PROMPT_CACHE = os.path.join(_PROJECT_DIR, ".manual_prompt.json")
MANUAL_RESULT_FILE = (
    os.path.join(_PROJECT_DIR, ".manual_result.txt")
    if web_mode()
    else "manual_result.txt"
)


def _build_prompt(chapter, context_text, pronoun_context, previous_chapters):
    return build_single_prompt(
        chapter,
        context_text,
        pronoun_context,
        previous_chapters,
        previous_heading="Các chương trước (Tham khảo văn phong):",
    )


def parse_manual_result():
    if not os.path.exists(MANUAL_RESULT_FILE):
        return None, None

    with open(MANUAL_RESULT_FILE, "r", encoding="utf-8") as file:
        text = re.sub(r"\\\#\\\#\\\#", "###", file.read().strip())

    if "###TITLE###" not in text or "###CONTENT###" not in text:
        return None, None
    title_start = text.find("###TITLE###") + len("###TITLE###")
    content_start = text.find("###CONTENT###")
    title = text[title_start:content_start].strip()
    raw_content = text[content_start + len("###CONTENT###") :]
    end = raw_content.find("###END###")
    content = raw_content[:end].strip() if end != -1 else raw_content.strip()
    return title, content


def _is_placeholder(value, placeholders):
    normalized = value.strip("<>").strip().lower()
    return normalized in {
        placeholder.strip("<>").strip().lower() for placeholder in placeholders
    }


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    previous_chapters = ""
    if os.path.exists(NOVEL_TXT):
        with open(NOVEL_TXT, "r", encoding="utf-8") as file:
            previous_chapters = file.read().strip()

    prompt = _build_prompt(
        chapter, context_text, pronoun_context, previous_chapters
    )
    if web_mode():
        os.makedirs(_PROJECT_DIR, exist_ok=True)
        temporary = MANUAL_PROMPT_CACHE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "chapter": f"{chapter['id']}.md",
                    "title": chapter.get("title", chapter["id"]),
                    "prompt": prompt,
                },
                file,
                ensure_ascii=False,
            )
        os.replace(temporary, MANUAL_PROMPT_CACHE)
    else:
        with open(MANUAL_PROMPT_FILE, "w", encoding="utf-8") as file:
            file.write(prompt)

    print(f"📖 Đang chờ dịch thủ công Chương {chapter_number}: {chapter['title']}")
    print("✅ Đã chuẩn bị prompt dịch thủ công.")

    manual_result = str(option("manual_result", "")).strip() if web_mode() else ""
    manual_result_ready = web_mode() and bool_option("manual_result_ready", False)
    if web_mode() and not manual_result and not manual_result_ready:
        print("Prompt đã sẵn sàng trong giao diện web.")
        return None

    if manual_result:
        with open(MANUAL_RESULT_FILE, "w", encoding="utf-8") as file:
            file.write(manual_result)
    elif not os.path.exists(MANUAL_RESULT_FILE):
        with open(MANUAL_RESULT_FILE, "w", encoding="utf-8") as file:
            file.write("###TITLE###\n\n###CONTENT###\n\n###END###")

    while True:
        if not web_mode():
            input(
                f"Nhấn ENTER khi bạn đã paste và lưu file "
                f"'{MANUAL_RESULT_FILE}' xong..."
            )

        title, content = parse_manual_result()
        if not title or not content:
            message = (
                "File kết quả sai định dạng hoặc chưa có dữ liệu. "
                "Cần đủ ###TITLE### và ###CONTENT###."
            )
            if web_mode():
                raise ValueError(message)
            print(f"⚠️ {message}")
            continue

        if _is_placeholder(
            title, ("<tiêu đề dịch>", "tiêu đề dịch", "<translated title>")
        ):
            message = "Tiêu đề vẫn là placeholder."
        elif _is_placeholder(
            content, ("<nội dung dịch>", "nội dung dịch", "<translated content>")
        ):
            message = "Nội dung vẫn là placeholder."
        else:
            print("✅ Đã đọc thành công bản dịch thủ công.")
            return title, content

        if web_mode():
            raise ValueError(message)
        print(f"⚠️ {message} Hãy cập nhật lại file kết quả.")


def run_translation():
    return run_single_translation(
        translate_chapter,
        RAW_DIR,
        TRANSLATED_DIR,
        CONTEXT_YAML,
    )


if __name__ == "__main__":
    try:
        print("🚀 Dịch tiểu thuyết thủ công theo file Markdown")
        print("=" * 50)
        while True:
            run_translation()
            raw_files = scan_md_dir(RAW_DIR)
            all_done = bool(raw_files) and all(
                is_translated(
                    os.path.splitext(os.path.basename(path))[0], TRANSLATED_DIR
                )
                for path in raw_files
            )
            if all_done:
                print("🎉 Đã dịch hết tất cả các chương!")
                break
            if web_mode():
                print("✅ Đã hoàn tất một bước dịch thủ công từ giao diện web.")
                break

            print(
                "\n⏳ Phím bất kỳ để tạo prompt chương tiếp theo, ESC để thoát."
            )
            while not msvcrt.kbhit():
                time.sleep(0.1)
            if msvcrt.getch() == b"\x1b":
                raise SystemExit
    except KeyboardInterrupt:
        print("\n⏹ Đã dừng bởi Ctrl + C")
    except SystemExit:
        pass
    finally:
        print("✅ Đã hoàn tất!")
