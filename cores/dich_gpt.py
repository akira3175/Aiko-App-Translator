"""
dich_gpt.py
===========
Dịch batch từ MD files (truyen/raw/*.md) → truyen/translated/*.md.
Logic y hệt dich_v3.py — chỉ thay Gemini web bằng ChatGPT web.

- Phân biệt đã dịch: file vx_cy_sz.md có trong cả raw/ và translated/
- Pipeline hậu dịch (fix_translation, pronouns, review) giữ nguyên hoàn toàn (qua Gemini API)
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
    CONTEXT_YAML,
    NOVEL_TXT,
    RAW_DIR,
    TRANSLATED_DIR,
    close_chatgpt_driver,
    generate_content_with_chatgpt,
    get_chatgpt_driver,
    is_translated,
    # Context
    scan_md_dir,
    setup_chatgpt_browser,
)
from cores.runtime_config import bool_option, int_option, stop_requested, web_mode
from cores.translation_prompts import build_batch_prompt
from cores.translation_workflows import run_batch_translation, translate_batch_with_web

# ============================================================
# ★ CẤU HÌNH RIÊNG
# ============================================================
BRANCH = 1  # Số chương dịch mỗi batch


# ==== PROMPT DỊCH BATCH (giữ nguyên từ dich_v3.py) ====


def _build_batch_prompt(batch, context_text, pronoun_context, pre_chapters):
    return build_batch_prompt(batch, context_text, pronoun_context, pre_chapters)


# ==== DỊCH BATCH (dùng ChatGPT web) ====


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
        generate=generate_content_with_chatgpt,
        reset_browser=lambda: get_chatgpt_driver().get("https://chatgpt.com/"),
        engine_name="ChatGPT web",
        require_boundaries=True,
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
        print("🚀 Dịch tiểu thuyết qua ChatGPT Web (GPT — Batch)")
        print("=" * 50)
        if not web_mode() or bool_option("open_browser_setup", True):
            setup_chatgpt_browser()

        consecutive_errors = 0
        while True:
            if stop_requested():
                print("Da dung truoc khi nhan batch tiep theo.")
                break
            try:
                run_translation()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                print(f"⚠️ Lỗi khi dịch: {e}")
                print(f"⚠️ Đã lỗi liên tiếp {consecutive_errors}/5 lần.")
                print(
                    "🧹 Đang dọn dẹp trình duyệt cũ để tránh mở nhiều cửa sổ Chrome..."
                )
                close_chatgpt_driver()

                if consecutive_errors >= 5:
                    print(
                        "❌ Dừng script do lỗi quá nhiều lần (có thể kẹt Captcha hoặc hết hạn đăng nhập)."
                    )
                    break

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
        close_chatgpt_driver()
        print("✅ Đã hoàn tất!")
