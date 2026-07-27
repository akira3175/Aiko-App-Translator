"""
review_all.py
=============
Review toàn bộ truyện đã dịch — ưu tiên phát hiện:
  1. Lỗi giới tính (gọi nhầm anh/chị, cậu/cô, hắn/nàng…)
  2. Lỗi xưng hô (không nhất quán hoặc sai mối quan hệ)
  3. Các lỗi khác (thuật ngữ, phong cách, logic)

Kết quả:
  - review.yaml          → chi tiết review từng chương
  - manual_check.yaml    → danh sách ID cần kiểm tra thủ công

Sử dụng:
  python cores/review_all.py

  Chạy script → nhập tham số theo hướng dẫn → nhấn Enter để dùng mặc định.
"""

import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import yaml

# Đảm bảo encoding UTF-8 cho stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Chuyển working directory về thư mục gốc dự án
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)

# Đảm bảo import được dich_utils dù chạy trực tiếp hay qua module
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Import từ dich_utils.py
from cores.dich_utils import (
    CONTEXT_YAML,
    RAW_DIR,
    REVIEW_YAML,
    TRANSLATED_DIR,
    _review_lock,
    call_gemini,
    load_context,
    # MD helpers
    scan_md_dir,
    switch_api_key,
)
from cores.runtime_config import bool_option, int_option, option, web_mode

# ============================================================
# ★ CẤU HÌNH MẶC ĐỊNH (có thể ghi đè bằng CLI args)
# ============================================================
MANUAL_CHECK_YAML = os.path.join(os.path.dirname(REVIEW_YAML), "manual_check.yaml")
DEFAULT_BATCH = 10  # Số chương gọi song song mỗi batch
DEFAULT_WORKERS = 10  # Số thread gọi API cùng lúc
REVIEW_MODEL = str(option("review_model", "gemini-3.1-flash-lite-preview"))
DEFAULT_SLEEP = 4  # Giây nghỉ giữa các batch
GENDER_SEVERITY = "nặng"  # Severity mặc định cho lỗi giới tính
ADDRESS_SEVERITY = "nặng"  # Severity mặc định cho lỗi xưng hô

# ============================================================
# ★ LOAD / SAVE HELPERS
# ============================================================


def load_review(path=REVIEW_YAML):
    """Load review.yaml hiện tại."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_review(data, path=REVIEW_YAML):
    """Ghi review.yaml (thread-safe)."""
    with _review_lock:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def load_manual_check(path=MANUAL_CHECK_YAML):
    """Load danh sách ID cần kiểm tra thủ công."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_manual_check(data, path=MANUAL_CHECK_YAML):
    """Ghi manual_check.yaml."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def add_to_manual_check(chapter_id, path=MANUAL_CHECK_YAML):
    """Thêm 1 ID vào manual_check.yaml nếu chưa có."""
    data = load_manual_check(path)
    if chapter_id not in data:
        data.append(chapter_id)
        save_manual_check(data, path)


# ============================================================
# ★ PROMPT REVIEW — ƯU TIÊN GIỚI TÍNH & XƯNG HÔ
# ============================================================


def build_review_prompt(
    chapter_id,
    chapter_number,
    raw_title,
    raw_content,
    title,
    content,
    context_text="",
):
    """Tạo prompt review chuyên sâu — ưu tiên giới tính & xưng hô."""
    prompt = f"""Bạn là chuyên gia review dịch thuật tiểu thuyết Hàn-Việt.
Nhiệm vụ: Đối chiếu sát bản gốc tiếng Hàn với bản dịch tiếng Việt và tìm lỗi. Không được phỏng đoán lỗi nếu bản gốc không chứng minh điều đó.

## ƯU TIÊN CAO NHẤT — Phải kiểm tra kỹ:

### 1. LỖI GIỚI TÍNH (severity: "nặng")
- Dùng sai đại từ giới tính: "anh ấy" cho nữ, "cô ấy" cho nam
- Dùng sai đại từ ngôi thứ 3 trong dẫn thoại: "hắn" cho nữ, "nàng" cho nam
- Nhầm lẫn "cậu" (nam) vs "cô" (nữ) trong dẫn truyện ngôi thứ ba
- Dịch sai giới tính qua cách miêu tả (ví dụ: miêu tả nam như nữ hoặc ngược lại)
- Nhầm vai trò giới trong hội thoại (ai nói câu gì)

### 2. LỖI XƯNG HÔ (severity: "nặng")
- Xưng hô không phù hợp mối quan hệ (ví dụ: bạn bè gọi "ngài", đồng nghiệp gọi "con")
- Thiếu nhất quán xưng hô trong cùng 1 chương (lúc gọi "cậu" lúc gọi "anh" cho cùng 1 người mà không có lý do)
- Xưng hô sai vai vế (em gái xưng "anh", anh trai xưng "em" khi không có lý do đặc biệt)
- Lẫn lộn ngôi xưng hô giữa các cặp nhân vật khác nhau

### 3. Lỗi khác (severity: "trung bình" hoặc "nhẹ")
- Thiếu câu, thiếu đoạn hoặc tự thêm nội dung không có trong bản gốc
- Dịch sai nghĩa, nhầm chủ thể, nhầm quan hệ hoặc sai sự kiện
- Thuật ngữ dịch sai/không nhất quán
- Phong cách dịch cứng nhắc, không tự nhiên
- Logic truyện bị sai
- Còn sót ký tự ngoại ngữ

## Thuật ngữ tham chiếu:
{context_text[:3000]}

## Thông tin chương:
- ID: {chapter_id}
- Số chương: {chapter_number}

## Bản gốc tiếng Hàn:
### Tiêu đề gốc:
{raw_title}

### Nội dung gốc:
{raw_content}

## Bản dịch tiếng Việt:
## Tiêu đề dịch:
{title}

## Nội dung dịch:
{content}

## YÊU CẦU OUTPUT:
Trả về JSON (KHÔNG markdown, KHÔNG giải thích thêm):
{{
  "chapter_id": "{chapter_id}",
  "overall_score": <1-10>,
  "issues": [
    {{
      "type": "thiếu nội dung|thêm nội dung|dịch sai|giới tính|xưng hô|thuật ngữ|phong cách|logic|ngoại ngữ",
      "severity": "nặng|trung bình|nhẹ",
      "original_kr": "đoạn tương ứng trong bản gốc tiếng Hàn",
      "original_vi": "đoạn lỗi trong bản dịch",
      "suggestion": "gợi ý sửa"
    }}
  ],
  "gender_ok": true/false,
  "address_ok": true/false,
  "summary": "nhận xét tổng quan 1-2 câu"
}}

Lưu ý:
- Nếu KHÔNG có lỗi giới tính, đặt "gender_ok": true
- Nếu KHÔNG có lỗi xưng hô, đặt "address_ok": true
- Nếu CÓ lỗi giới tính hoặc xưng hô, PHẢI liệt kê chi tiết trong issues
- Chỉ trả về JSON, không giải thích"""

    return prompt


# ============================================================
# ★ GỌI API REVIEW (có retry)
# ============================================================


def call_review_api(prompt):
    """Gọi Gemini API để review. Retry vô hạn cho đến khi thành công."""
    attempt = 0
    while True:
        attempt += 1
        try:
            text = call_gemini(prompt, model=REVIEW_MODEL, temperature=0.4).strip()
            if not text:
                print(f"  ⚠️ Response rỗng, thử lại (lần {attempt})...")
                time.sleep(5)
                continue

            # Parse JSON
            clean = re.sub(r"```json\s*|\s*```", "", text).strip()
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                return json.loads(clean[start : end + 1])
            else:
                print(
                    f"  ⚠️ Không tìm thấy JSON trong response, thử lại (lần {attempt})..."
                )
                time.sleep(3)
                continue

        except json.JSONDecodeError as e:
            print(f"  ⚠️ Lỗi parse JSON: {e}, thử lại (lần {attempt})...")
            time.sleep(3)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                switch_api_key()
                wait = min(30 + attempt * 10, 120)
                print(f"  🔄 Lỗi 429! Đổi key, chờ {wait}s (lần {attempt})...")
                time.sleep(wait)
            elif any(code in err for code in ["500", "502", "503", "504"]):
                wait = min(10 + attempt * 5, 60)
                print(f"  ⚠️ Lỗi 5xx, chờ {wait}s (lần {attempt})...")
                time.sleep(wait)
            else:
                print(f"  ⚠️ Lỗi: {err}, chờ 15s (lần {attempt})...")
                time.sleep(15)


# ============================================================
# ★ XỬ LÝ KẾT QUẢ REVIEW
# ============================================================


def process_review_result(
    chapter_id, chapter_number, review_data, review_store, manual_list
):
    """
    Xử lý kết quả review:
    - Lưu vào review_store (dict)
    - Nếu có lỗi giới tính hoặc xưng hô nặng → thêm vào manual_list
    """
    if not review_data:
        return

    issues = review_data.get("issues", [])
    gender_ok = review_data.get("gender_ok", True)
    address_ok = review_data.get("address_ok", True)

    # Lưu vào review store
    review_store[chapter_id] = {
        "chapter_number": chapter_number,
        "score": review_data.get("overall_score"),
        "issue_count": len(issues),
        "gender_ok": gender_ok,
        "address_ok": address_ok,
        "issues": issues,
        "summary": str(review_data.get("summary", ""))[:1500],
    }

    # Kiểm tra xem có cần manual check không
    needs_manual = False

    # Nếu API báo gender/address có vấn đề
    if not gender_ok or not address_ok:
        needs_manual = True

    # Mọi lỗi nặng/trung bình cần được kiểm tra thủ công; đặc biệt là lỗi
    # thiếu nội dung, dịch sai, giới tính và xưng hô.
    for issue in issues:
        severity = issue.get("severity", "").lower()
        if severity in ("nặng", "trung bình"):
            needs_manual = True
            break

    if needs_manual:
        if chapter_id not in manual_list:
            manual_list.append(chapter_id)
        print(f"  🔴 {chapter_id} — CẦN KIỂM TRA THỦ CÔNG (giới tính/xưng hô)")
    else:
        score = review_data.get("overall_score", "?")
        print(f"  ✅ {chapter_id} — Score: {score}/10, {len(issues)} issues")


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
    print(f"{'─' * 65}\n")

    # Load dữ liệu bản dịch từ truyen/translated/*.md
    print("\n📂 Đang tải bản dịch từ MD...")
    translated_files = scan_md_dir(TRANSLATED_DIR)
    if not translated_files:
        print(f"  Không tìm thấy file dịch nào trong {TRANSLATED_DIR}")
        return

    # Ghép từng file dịch với đúng file raw cùng tên để review đối chiếu.
    chapters = []
    missing_raw = []
    for filepath in translated_files:
        chapter_id = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
        # Dòng đầu = tiêu đề (# ...)
        title = ""
        content_lines = []
        for line in raw.split("\n"):
            stripped = line.strip()
            if not title and stripped.startswith("# "):
                title = stripped[2:]
            elif stripped.startswith("!["):
                pass  # bỏ placeholder ảnh
            else:
                if stripped:
                    content_lines.append(stripped)
        content = "\n".join(content_lines).strip()
        raw_path = os.path.join(RAW_DIR, os.path.basename(filepath))
        raw_title = ""
        raw_content = ""
        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            raw_lines = raw_text.splitlines()
            for line in raw_lines:
                stripped = line.strip()
                if not raw_title and stripped.startswith("# "):
                    raw_title = stripped[2:].strip()
                elif not stripped.startswith("!["):
                    raw_content += line + "\n"
            raw_content = raw_content.strip()
        else:
            missing_raw.append(chapter_id)
        if content:  # bỏ file rỗng
            chapters.append(
                {
                    "id": chapter_id,
                    "raw_title": raw_title,
                    "raw_content": raw_content,
                    "title_translation": title,
                    "translation": content,
                }
            )

    if missing_raw:
        sample = ", ".join(missing_raw[:5])
        print(f"  ⚠️ Thiếu raw cho {len(missing_raw)} chương ({sample})")

    context_text = load_context(CONTEXT_YAML)
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
    review_store = load_review(REVIEW_YAML)
    manual_list = load_manual_check(MANUAL_CHECK_YAML)
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
        # Chapter number: tích từ sorted index hoặc parse từ id vx_cy_sz
        m = re.search(r"_c(\d+)_", chapter_id)
        chapter_number = int(m.group(1)) + 1 if m else i + 1
        title = chapter.get("title_translation", "")
        content = chapter.get("translation", "")
        raw_title = chapter.get("raw_title", "")
        raw_content = chapter.get("raw_content", "")
        if not content.strip():
            continue
        if not raw_content.strip():
            print(f"  ⚠️ Bỏ qua {chapter_id}: không có nội dung raw để đối chiếu")
            continue
        content_trimmed = content[:8000] if len(content) > 8000 else content
        raw_trimmed = raw_content[:8000] if len(raw_content) > 8000 else raw_content
        review_items.append(
            (
                chapter_id,
                chapter_number,
                raw_title,
                raw_trimmed,
                title,
                content_trimmed,
            )
        )

    total_items = len(review_items)
    num_batches = (total_items + batch_size - 1) // batch_size

    # Bắt đầu review
    print(f"\n{'─' * 65}")
    print(
        f"🔍 BẮT ĐẦU REVIEW ({total_items} chương, {num_batches} batch × {batch_size}, pipeline liên tục)"
    )
    print(f"{'─' * 65}\n")

    reviewed = 0
    errors = 0
    manual_added = len(manual_list)
    _result_lock = threading.Lock()
    _save_counter = [0]  # mutable để dùng trong callback

    def _review_one(global_order, item_info):
        """Worker: review 1 chương, trả về (global_order, cid, cnum, result)."""
        cid, cnum, raw_title, raw_content, title, content = item_info
        prompt = build_review_prompt(
            cid,
            cnum,
            raw_title,
            raw_content,
            title,
            content,
            context_text,
        )
        result = call_review_api(prompt)
        return (global_order, cid, cnum, result)

    def _on_done(future):
        """Callback: xử lý kết quả ngay khi API trả về (bất đồng bộ)."""
        nonlocal reviewed, errors
        try:
            global_order, cid, cnum, result = future.result()
            with _result_lock:
                process_review_result(cid, cnum, result, review_store, manual_list)
                reviewed += 1
                _save_counter[0] += 1
                # Auto-save sau mỗi batch_size kết quả
                if _save_counter[0] >= batch_size:
                    save_review(review_store, REVIEW_YAML)
                    save_manual_check(manual_list, MANUAL_CHECK_YAML)
                    print(f"  💾 Auto-save ({reviewed}/{total_items} reviewed)")
                    _save_counter[0] = 0
        except Exception as e:
            with _result_lock:
                errors += 1
            print(f"  ❌ Exception: {e}")

    # ── Pipeline: gửi liên tục, không chờ batch trước hoàn thành ──
    # Dùng 1 executor duy nhất, đủ worker cho nhiều batch chồng lấp
    max_concurrent = workers * 3  # headroom cho overlap giữa các batch
    executor = ThreadPoolExecutor(max_workers=max_concurrent)
    all_futures = []

    try:
        for batch_idx in range(num_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, total_items)
            batch = review_items[batch_start:batch_end]
            batch_num = batch_idx + 1

            # Gửi batch — fire & forget
            for local_idx, item in enumerate(batch):
                global_order = batch_start + local_idx
                f = executor.submit(_review_one, global_order, item)
                f.add_done_callback(_on_done)
                all_futures.append(f)

            print(
                f"  🚀 Đã gửi batch {batch_num}/{num_batches} "
                f"({len(batch)} chương: {batch_start + 1}~{batch_end})"
            )

            # Nghỉ + đổi key rồi gửi tiếp (KHÔNG chờ batch trước xong)
            if batch_idx < num_batches - 1:
                time.sleep(sleep_between)
                switch_api_key()

        # Chờ tất cả hoàn thành
        print(f"\n  ⏳ Đã gửi hết {total_items} request, đang chờ kết quả còn lại...")
        wait(all_futures)

    finally:
        executor.shutdown(wait=True)

    # Lưu lần cuối (đảm bảo không mất dữ liệu)
    save_review(review_store, REVIEW_YAML)
    save_manual_check(manual_list, MANUAL_CHECK_YAML)

    # Thống kê
    new_manual = len(manual_list) - manual_added
    print(f"\n{'=' * 65}")
    print(f"📊 KẾT QUẢ REVIEW")
    print(f"{'=' * 65}")
    print(f"  ✅ Đã review:         {reviewed}/{len(to_review)} chương")
    print(f"  ❌ Lỗi API:           {errors} chương")
    print(f"  🔴 Cần kiểm tra:      {new_manual} chương mới thêm")
    print(f"  📋 Tổng manual check: {len(manual_list)} chương")
    print(f"\n  📄 Review:       {os.path.abspath(REVIEW_YAML)}")
    print(f"  📄 Manual check: {os.path.abspath(MANUAL_CHECK_YAML)}")

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
