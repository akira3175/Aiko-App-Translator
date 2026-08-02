"""
dich_v3_md.py
=============
Dịch batch từ MD files (truyen/raw/*.md) → truyen/translated/*.md.

- Phân biệt đã dịch: file vx_cy_sz.md có trong cả raw/ và translated/
- Pipeline hậu dịch (fix_translation, pronouns, review) giữ nguyên hoàn toàn
"""

import msvcrt
import os
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
from cores.runtime_config import bool_option, int_option, stop_requested, web_mode
from cores.translation_prompts import build_batch_prompt
from cores.translation_workflows import run_batch_translation, translate_batch_with_web

# ============================================================
# ★ CẤU HÌNH RIÊNG (giống dich_v3.py)
# ============================================================
BRANCH = 2  # Số chương dịch mỗi batch


# ==== PROMPT DỊCH BATCH (giữ nguyên từ dich_v3.py) ====


def _build_batch_prompt(batch, context_text, pronoun_context, pre_chapters):
    return build_batch_prompt(
        batch, context_text, pronoun_context, pre_chapters, include_start=False
    )


# ==== DỊCH BATCH (copy từ dich_v3.py, không thay đổi) ====


def translate_chapters(
    batch, start_chapter_number, context_text="", pronoun_context=""
):
    return translate_batch_with_web(
        batch,
        start_chapter_number,
        context_text,
        pronoun_context,
        novel_text_path=NOVEL_TXT,
        build_prompt=_build_batch_prompt,
        generate=generate_content_with_selenium,
        reset_browser=lambda: get_gemini_driver().get("https://gemini.google.com/app"),
        engine_name="Gemini web",
        require_boundaries=False,
    )


# ==== QUY TRÌNH DỊCH (MD thay YAML) ====


def run_translation(
    raw_dir=RAW_DIR, translated_dir=TRANSLATED_DIR, context_path=CONTEXT_YAML
):
    """Run this engine for the next untranslated batch."""
    return run_batch_translation(
        translate_chapters,
        int_option("batch_size", BRANCH, minimum=1),
        raw_dir,
        translated_dir,
        context_path,
    )


# ==== MAIN LOOP ====

if __name__ == "__main__":
    try:
        print("🚀 Dịch tiểu thuyết qua Gemini Web (V3 MD — Batch)")
        print("=" * 50)
        if not web_mode() or bool_option("open_browser_setup", True):
            setup_gemini_browser()

        while True:
            if stop_requested():
                print("Da dung truoc khi nhan batch tiep theo.")
                break
            try:
                run_translation()
            except Exception as e:
                print(f"⚠️ Lỗi khi dịch: {e}")
                print("⏳ Chờ 10s rồi thử lại...")
                time.sleep(10)
                continue

            # Kiểm tra đã dịch hết chưa
            if stop_requested():
                print("Da dich xong batch hien tai va dung theo yeu cau.")
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
                print("✅ Đã xử lý một batch theo cấu hình web.")
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
