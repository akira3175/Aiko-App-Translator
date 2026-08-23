"""
Full-novel review entrypoint
============================
Review toàn bộ truyện đã dịch — ưu tiên phát hiện:
  1. Lỗi giới tính (gọi nhầm anh/chị, cậu/cô, hắn/nàng…)
  2. Lỗi xưng hô (không nhất quán hoặc sai mối quan hệ)
  3. Các lỗi khác (thuật ngữ, phong cách, logic)

Kết quả:
  - review.json          → chi tiết review từng chương
  - manual_check.json    → danh sách ID cần kiểm tra thủ công

Sử dụng:
  python -m cores.full_review

  Chạy script → nhập tham số theo hướng dẫn → nhấn Enter để dùng mặc định.
"""

import io
import os
import sys

# Đảm bảo encoding UTF-8 cho stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Chuyển working directory về thư mục gốc dự án
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(_PROJECT_ROOT)

# Đảm bảo import được package cores dù chạy trực tiếp hay qua module.
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from cores.config import CONTEXT_JSON, RAW_DIR, REVIEW_JSON, TRANSLATED_DIR
from cores.context import load_context_text as load_context
from cores.full_review import (
    call_review_api as _call_review_api,
    load_manual_check,
    load_review,
    load_review_chapters,
    prepare_review_item,
    run_review_items,
)
from cores.config.runtime import bool_option, int_option, option, web_mode
from cores.stages import browser_lifecycle, stage_model_and_thinking, stage_provider

# ============================================================
# ★ CẤU HÌNH MẶC ĐỊNH (có thể ghi đè bằng CLI args)
# ============================================================
MANUAL_CHECK_JSON = os.path.join(os.path.dirname(REVIEW_JSON), "manual_check.json")
DEFAULT_BATCH = 10  # Số chương gọi song song mỗi batch
DEFAULT_WORKERS = 10  # Số thread gọi API cùng lúc
REVIEW_PROVIDER = stage_provider("review", get_option=option)
if REVIEW_PROVIDER == "off":
    REVIEW_MODEL, REVIEW_THINKING = "", ""
else:
    REVIEW_MODEL, REVIEW_THINKING = stage_model_and_thinking(
        "review", REVIEW_PROVIDER, get_option=option
    )
DEFAULT_SLEEP = 4  # Giây nghỉ giữa các batch
GENDER_SEVERITY = "nặng"  # Severity mặc định cho lỗi giới tính
ADDRESS_SEVERITY = "nặng"  # Severity mặc định cho lỗi xưng hô

def call_review_api(prompt):
    """Backward-compatible API using the configured review provider."""
    return _call_review_api(prompt, REVIEW_PROVIDER)


# ============================================================
# ★ MAIN
# ============================================================


def _input_int(prompt, default):
    """Hỏi người dùng nhập số nguyên, Enter = dùng mặc định."""
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"  ⚠️ Không hợp lệ, dùng mặc định: {default}")
        return default


def main():
    if REVIEW_PROVIDER == "off" or REVIEW_MODEL.strip().lower() in {"", "none"}:
        print("Bỏ qua review toàn bộ vì chưa cấu hình engine hoặc model.")
        return
    print("=" * 65)
    print("📖 REVIEW TOÀN BỘ TRUYỆN — Ưu tiên Giới Tính & Xưng Hô")
    print("=" * 65)
    if web_mode():
        print("\n⚙️  Đang dùng cấu hình từ giao diện web.\n")
        start_chap = int_option("start", 1, minimum=1)
        end_chap = int_option("end", None, minimum=1)
        force = bool_option("force", False)
        batch_size = int_option("batch_size", DEFAULT_BATCH, minimum=1)
        workers = int_option("workers", DEFAULT_WORKERS, minimum=1)
        sleep_between = int_option("sleep", DEFAULT_SLEEP, minimum=0)
    else:
        print("\n⚙️  CẤU HÌNH (nhấn Enter để dùng mặc định):\n")
        start_chap = _input_int("  Bắt đầu từ chương thứ [1]: ", 1)
        end_chap_raw = input("  Kết thúc tại chương thứ [cuối]: ").strip()
        end_chap = int(end_chap_raw) if end_chap_raw else None
        force_raw = input("  Review lại chương đã có? (y/N) [N]: ").strip().lower()
        force = force_raw in ("y", "yes", "1")
        batch_size = _input_int(
            f"  Số chương mỗi batch [{DEFAULT_BATCH}]: ", DEFAULT_BATCH
        )
        workers = _input_int(
            f"  Số thread song song [{DEFAULT_WORKERS}]: ", DEFAULT_WORKERS
        )
        sleep_between = _input_int(
            f"  Giây nghỉ giữa các batch [{DEFAULT_SLEEP}]: ", DEFAULT_SLEEP
        )

    print(f"\n{'─' * 65}")
    print(f"  ▸ Phạm vi:  {start_chap} → {'cuối' if end_chap is None else end_chap}")
    print(f"  ▸ Force:    {'Có' if force else 'Không'}")
    print(f"  ▸ Batch:    {batch_size} | Workers: {workers} | Sleep: {sleep_between}s")
    print(f"  ▸ Engine:   {REVIEW_PROVIDER} | Model: {REVIEW_MODEL}")
    print(f"{'─' * 65}\n")

    # Load dữ liệu bản dịch từ truyen/translated/*.md
    print("\n📂 Đang tải bản dịch từ MD...")
    chapters, missing_raw = load_review_chapters(RAW_DIR, TRANSLATED_DIR)
    if not chapters:
        print(f"  Không tìm thấy file dịch nào trong {TRANSLATED_DIR}")
        return

    if missing_raw:
        sample = ", ".join(missing_raw[:5])
        print(f"  ⚠️ Thiếu raw cho {len(missing_raw)} chương ({sample})")

    context_text = load_context(CONTEXT_JSON)
    total = len(chapters)
    print(f"  Tổng chương dịch: {total}")

    # Áp dụng range
    start_idx = max(0, start_chap - 1)
    end_idx = min(total, end_chap) if end_chap else total
    to_review = chapters[start_idx:end_idx]
    print(
        f"  Phạm vi review: chương {start_idx + 1} → {end_idx} ({len(to_review)} chương)"
    )

    # Load review & manual check hiện tại
    review_store = load_review(REVIEW_JSON)
    manual_list = load_manual_check(MANUAL_CHECK_JSON)
    existing_count = len(review_store)
    print(f"  Review hiện có: {existing_count} chương")
    print(f"  Manual check hiện có: {len(manual_list)} chương")

    # Lọc chương cần review
    if not force:
        to_review = [ch for ch in to_review if ch.get("id", "") not in review_store]
        print(f"  Chương cần review (chưa có): {len(to_review)}")
    else:
        print(f"  Chương cần review (force all): {len(to_review)}")

    if not to_review:
        print("\n✅ Không có chương nào cần review. Dùng --force để review lại.")
        return

    # Chuẩn bị danh sách review items (id, number, title, content)
    review_items = []
    for i, chapter in enumerate(to_review):
        chapter_id = chapter.get("id", f"unknown_{i}")
        if not chapter.get("translation", "").strip():
            continue
        if not chapter.get("raw_content", "").strip():
            print(f"  ⚠️ Bỏ qua {chapter_id}: không có nội dung raw để đối chiếu")
            continue
        review_items.append(prepare_review_item(chapter, i))

    total_items = len(review_items)
    num_batches = (total_items + batch_size - 1) // batch_size

    # Bắt đầu review
    print(f"\n{'─' * 65}")
    print(
        f"🔍 BẮT ĐẦU REVIEW ({total_items} chương, {num_batches} batch × {batch_size}, pipeline liên tục)"
    )
    print(f"{'─' * 65}\n")

    manual_added = len(manual_list)
    setup_browser, close_browser = browser_lifecycle(REVIEW_PROVIDER)
    should_setup = not web_mode() or bool_option("open_browser_setup", True)
    if setup_browser and should_setup:
        setup_browser()
    try:
        reviewed, errors = run_review_items(
            review_items,
            context_text,
            review_store,
            manual_list,
            provider=REVIEW_PROVIDER,
            batch_size=batch_size,
            workers=workers,
            sleep_between=sleep_between,
            review_path=REVIEW_JSON,
            manual_path=MANUAL_CHECK_JSON,
        )
    finally:
        if close_browser:
            close_browser()

    # Thống kê
    new_manual = len(manual_list) - manual_added
    print(f"\n{'=' * 65}")
    print(f"📊 KẾT QUẢ REVIEW")
    print(f"{'=' * 65}")
    print(f"  ✅ Đã review:         {reviewed}/{len(to_review)} chương")
    print(f"  ❌ Lỗi API:           {errors} chương")
    print(f"  🔴 Cần kiểm tra:      {new_manual} chương mới thêm")
    print(f"  📋 Tổng manual check: {len(manual_list)} chương")
    print(f"\n  📄 Review:       {os.path.abspath(REVIEW_JSON)}")
    print(f"  📄 Manual check: {os.path.abspath(MANUAL_CHECK_JSON)}")

    # Thống kê lỗi giới tính/xưng hô
    gender_issues = 0
    address_issues = 0
    for cid, rdata in review_store.items():
        if not rdata.get("gender_ok", True):
            gender_issues += 1
        if not rdata.get("address_ok", True):
            address_issues += 1

    if gender_issues or address_issues:
        print(f"\n  ⚠️ Lỗi giới tính: {gender_issues} chương")
        print(f"  ⚠️ Lỗi xưng hô:  {address_issues} chương")

    print(f"\n{'=' * 65}")
    print("✅ HOÀN TẤT!")


if __name__ == "__main__":
    main()
