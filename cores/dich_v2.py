"""
dich_v2_md.py
=============
Dịch TỪNG CHƯƠNG một từ MD files (truyen/raw/*.md) → truyen/translated/*.md.

- Phân biệt đã dịch: file vx_cy_sz.md có trong cả raw/ và translated/
- Pipeline hậu dịch (fix_translation, pronouns, review) giữ nguyên hoàn toàn
"""

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
    # Constants
    CONTEXT_YAML,
    NOVEL_TXT,
    RAW_DIR,
    TRANSLATED_DIR,
    close_gemini_driver,
    generate_content_with_selenium,
    get_gemini_driver,
    is_translated,
    # Context
    scan_md_dir,
    # Selenium
    setup_gemini_browser,
)
from cores.runtime_config import bool_option, chapter_limit, stop_requested, web_mode
from cores.translation_prompts import build_single_prompt
from cores.translation_workflows import run_single_translation

# ==== PROMPT DỊCH ĐƠN CHƯƠNG (copy từ dich_v2.py) ====


def _build_prompt(chapter, context_text, pronoun_context, pre_chapters):
    return build_single_prompt(chapter, context_text, pronoun_context, pre_chapters)


# ==== DỊCH ĐƠN CHƯƠNG ====


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    """Dịch một chương, trả về (title_trans, content_trans)."""
    max_retries = 3

    for attempt in range(max_retries):
        pre_chapters = ""
        if os.path.exists(NOVEL_TXT):
            with open(NOVEL_TXT, "r", encoding="utf-8") as f:
                pre_chapters = f.read().strip()

        prompt = _build_prompt(chapter, context_text, pronoun_context, pre_chapters)

        if attempt > 0:
            print(f"🔄 Thử lại lần {attempt + 1}/{max_retries}...")
            driver = get_gemini_driver()
            driver.get("https://gemini.google.com/app")
            time.sleep(3)

        print(
            f"✨ Đang dịch Chương {chapter_number}: {chapter['id']} qua Gemini web..."
        )
        text = generate_content_with_selenium(prompt)

        if not text:
            text = ""
        text = re.sub(r"\\\#\\\#\\\#", "###", text)

        if "###TITLE###" in text and "###CONTENT###" in text:
            title_start = text.find("###TITLE###") + len("###TITLE###")
            content_marker_pos = text.find("###CONTENT###")
            title_part = text[title_start:content_marker_pos].strip()
            raw_content = text[content_marker_pos + len("###CONTENT###") :]
            end_pos = raw_content.find("###END###")
            content_part = (
                raw_content[:end_pos].strip() if end_pos != -1 else raw_content.strip()
            )

            placeholder_titles = [
                "<tiêu đề dịch>",
                "tiêu đề dịch",
                "<translated title>",
            ]
            placeholder_contents = [
                "<nội dung dịch>",
                "nội dung dịch",
                "<translated content>",
            ]
            title_is_ph = title_part.strip("<>").strip().lower() in [
                p.strip("<>").strip().lower() for p in placeholder_titles
            ]
            content_is_ph = content_part.strip("<>").strip().lower() in [
                p.strip("<>").strip().lower() for p in placeholder_contents
            ]

            if title_is_ph or content_is_ph:
                print(f"⚠️ AI trả về placeholder (lần {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    raise ValueError(
                        f"AI trả về placeholder cho chương {chapter_number} sau {max_retries} lần thử"
                    )

            return title_part, content_part
        else:
            print(
                f"⚠️ Response sai định dạng (lần {attempt + 1}), "
                "không tìm thấy ###TITLE### và ###CONTENT###"
            )
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            else:
                raise ValueError(
                    f"Không thể dịch chương {chapter_number} sau {max_retries} lần thử"
                )

    raise ValueError(f"Không thể dịch chương {chapter_number}")


# ==== QUY TRÌNH DỊCH (MD thay YAML) ====


def run_translation(
    raw_dir=RAW_DIR, translated_dir=TRANSLATED_DIR, context_path=CONTEXT_YAML
):
    """Run this engine for the next untranslated chapter."""
    return run_single_translation(
        translate_chapter, raw_dir, translated_dir, context_path
    )


# ==== MAIN LOOP ====

if __name__ == "__main__":
    try:
        print("🚀 Dịch tiểu thuyết qua Gemini Web (V2 MD — Đơn chương)")
        print("=" * 50)
        if not web_mode() or bool_option("open_browser_setup", True):
            setup_gemini_browser()

        limit = chapter_limit()
        processed = 0
        while True:
            if stop_requested():
                print("Da dung truoc khi nhan chuong tiep theo.")
                break
            try:
                processed += run_translation() or 0
            except Exception as e:
                print(f"⚠️ Lỗi khi dịch: {e}")
                print("⏳ Chờ 10s rồi thử lại...")
                time.sleep(10)
                continue

            # Kiểm tra đã dịch hết chưa
            if stop_requested():
                print("Da dich xong chuong hien tai va dung theo yeu cau.")
                break
            raw_files = scan_md_dir(RAW_DIR)
            all_done = all(
                is_translated(os.path.splitext(os.path.basename(p))[0], TRANSLATED_DIR)
                for p in raw_files
            )
            if all_done:
                print("🎉 Đã dịch hết tất cả các chương!")
                break

            if web_mode() and limit is not None and processed >= limit:
                print(f"✅ Đã xử lý {processed} chương theo cấu hình web.")
                break

            print("⏳ Đang chuẩn bị dịch chương tiếp theo... (nhấn Enter để dừng)")
            for _ in range(30):
                time.sleep(0.1)
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b"\r":
                        print("🚪 Đã dừng theo yêu cầu (Enter).")
                        raise SystemExit

    except KeyboardInterrupt:
        print("\n⏹ Đã dừng bởi Ctrl + C")
    except SystemExit:
        pass
    finally:
        print("\n🌐 Đang đóng trình duyệt...")
        close_gemini_driver()
        print("✅ Đã hoàn tất!")
