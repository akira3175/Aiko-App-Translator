"""
dich_v1.py
==========
Dịch TỪNG CHƯƠNG một từ MD files (truyen/raw/*.md) → truyen/translated/*.md.
Giống dich_v2.py nhưng dùng Gemini API thay vì Selenium web — không cần browser.

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
    POLISH_MODEL,
    RAW_DIR,
    TRANSLATED_DIR,
    # API
    call_gemini,
    is_translated,
    # Context
    log_api_call,
    # Pipeline hậu dịch
    scan_md_dir,
    switch_api_key,
)
from cores.runtime_config import bool_option, option, stop_requested, web_mode
from cores.translation_prompts import build_single_prompt
from cores.translation_workflows import run_single_translation

# Model dùng cho dịch chính — có thể chỉnh tại đây
TRANSLATE_MODEL = str(option("translate_model", "gemini-3.5-flash"))


# ==== PROMPT DỊCH ĐƠN CHƯƠNG ====


def _build_prompt(chapter, context_text, pronoun_context, pre_chapters):
    return build_single_prompt(
        chapter, context_text, pronoun_context, pre_chapters, detailed_pronouns=False
    )


# ==== DỊCH ĐƠN CHƯƠNG (API) ====


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    """Dịch một chương qua Gemini API, trả về (title_trans, content_trans)."""
    max_retries = 3

    for attempt in range(max_retries):
        pre_chapters = ""
        if os.path.exists(NOVEL_TXT):
            with open(NOVEL_TXT, "r", encoding="utf-8") as f:
                pre_chapters = f.read().strip()

        prompt = _build_prompt(chapter, context_text, pronoun_context, pre_chapters)

        if attempt > 0:
            print(f"🔄 Thử lại lần {attempt + 1}/{max_retries}...")

        print(
            f"✨ Đang dịch Chương {chapter_number}: {chapter['id']} qua API ({TRANSLATE_MODEL})..."
        )

        try:
            text = call_gemini(prompt, model=TRANSLATE_MODEL, temperature=0.5)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                switch_api_key()
                wait = min(30 + attempt * 15, 90)
                print(f"  ⚠️ Lỗi 429, đổi key, chờ {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"  ⚠️ Lỗi API: {err}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                raise

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
                    log_api_call(
                        chapter.get("id", f"chapter_{chapter_number}"),
                        "translate",
                        TRANSLATE_MODEL,
                        prompt,
                        text,
                        ok=False,
                    )
                    raise ValueError(
                        f"AI trả về placeholder cho chương {chapter_number} sau {max_retries} lần thử"
                    )

            log_api_call(
                chapter.get("id", f"chapter_{chapter_number}"),
                "translate",
                TRANSLATE_MODEL,
                prompt,
                text,
                ok=True,
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
                log_api_call(
                    chapter.get("id", f"chapter_{chapter_number}"),
                    "translate",
                    TRANSLATE_MODEL,
                    prompt,
                    text,
                    ok=False,
                )
                raise ValueError(
                    f"Không thể dịch chương {chapter_number} sau {max_retries} lần thử"
                )

    raise ValueError(f"Không thể dịch chương {chapter_number}")


# ==== QUY TRÌNH DỊCH ====


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
        print("🚀 Dịch tiểu thuyết qua Gemini API (V1 — Đơn chương)")
        print("=" * 50)
        print(f"📡 Model dịch chính: {TRANSLATE_MODEL}")
        print(f"📡 Model hậu dịch : {POLISH_MODEL}")
        print("=" * 50)

        while True:
            if stop_requested():
                print("Da dung truoc khi nhan chuong tiep theo.")
                break
            try:
                run_translation()
            except Exception as e:
                print(f"⚠️ Lỗi khi dịch: {e}")
                print("⏳ Chờ 15s rồi thử lại...")
                time.sleep(15)
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

            if web_mode():
                if bool_option("run_until_complete", False):
                    continue
                print("✅ Đã xử lý một chương theo cấu hình web.")
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
        print("\n✅ Hoàn tất!")
