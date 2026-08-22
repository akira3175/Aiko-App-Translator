"""Prepare prompts and accept results for manual chapter translation."""

import json
import msvcrt
import os
import time

from cores.chapters.files import is_translated, scan_md_dir
from cores.config import CONTEXT_JSON, NOVEL_TXT, RAW_DIR, TRANSLATED_DIR
from cores.manual.results import parse_manual_result_text
from cores.config.runtime import bool_option, option, web_mode
from cores.translation.prompts import build_single_prompt
from cores.translation.runner import run_single_translation


MANUAL_PROMPT_FILE = "manual_prompt.txt"
PROJECT_DIR = os.path.dirname(RAW_DIR)
MANUAL_PROMPT_CACHE = os.path.join(PROJECT_DIR, ".manual_prompt.json")
MANUAL_RESULT_FILE = (
    os.path.join(PROJECT_DIR, ".manual_result.txt") if web_mode() else "manual_result.txt"
)


def build_prompt(chapter, context_text, pronoun_context, previous_chapters):
    return build_single_prompt(
        chapter,
        context_text,
        pronoun_context,
        previous_chapters,
        previous_heading="Các chương trước (Tham khảo văn phong):",
    )


def parse_manual_result(path=MANUAL_RESULT_FILE):
    if not os.path.exists(path):
        raise ValueError("Chưa có file kết quả dịch thủ công.")
    with open(path, "r", encoding="utf-8") as file:
        return parse_manual_result_text(file.read())


def _save_prompt(chapter, prompt):
    if web_mode():
        os.makedirs(PROJECT_DIR, exist_ok=True)
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
        return
    with open(MANUAL_PROMPT_FILE, "w", encoding="utf-8") as file:
        file.write(prompt)


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    previous = ""
    if os.path.exists(NOVEL_TXT):
        with open(NOVEL_TXT, "r", encoding="utf-8") as file:
            previous = file.read().strip()
    _save_prompt(chapter, build_prompt(chapter, context_text, pronoun_context, previous))
    print(f"📖 Đang chờ dịch thủ công Chương {chapter_number}: {chapter['title']}")

    manual_result = str(option("manual_result", "")).strip() if web_mode() else ""
    ready = web_mode() and bool_option("manual_result_ready", False)
    if web_mode() and not manual_result and not ready:
        print("Prompt đã sẵn sàng trong giao diện web.")
        return None
    if manual_result:
        with open(MANUAL_RESULT_FILE, "w", encoding="utf-8") as file:
            file.write(manual_result)

    while True:
        if not web_mode():
            input(f"Nhấn ENTER sau khi lưu '{MANUAL_RESULT_FILE}'...")
        try:
            result = parse_manual_result()
        except ValueError as error:
            if web_mode():
                raise
            print(f"⚠️ {error}")
            continue
        print("✅ Đã đọc thành công bản dịch thủ công.")
        return result


def run_translation():
    return run_single_translation(
        translate_chapter, RAW_DIR, TRANSLATED_DIR, CONTEXT_JSON
    )


def main():
    print("🚀 Dịch tiểu thuyết thủ công theo file Markdown")
    try:
        while True:
            run_translation()
            raw_files = scan_md_dir(RAW_DIR)
            if raw_files and all(
                is_translated(os.path.splitext(os.path.basename(path))[0], TRANSLATED_DIR)
                for path in raw_files
            ):
                print("🎉 Đã dịch hết tất cả các chương!")
                break
            if web_mode():
                break
            print("Phím bất kỳ để tạo prompt tiếp theo, ESC để thoát.")
            while not msvcrt.kbhit():
                time.sleep(0.1)
            if msvcrt.getch() == b"\x1b":
                break
    except KeyboardInterrupt:
        print("\n⏹ Đã dừng bởi Ctrl + C")
    finally:
        print("✅ Đã hoàn tất!")
