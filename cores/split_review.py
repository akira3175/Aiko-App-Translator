"""
split_review.py
===============
Tách review.yaml thành các file theo điểm số:
  - review_9.yaml   : điểm 9 - 9.9
  - review_8.yaml   : điểm 8 - 8.9
  - review_low.yaml : điểm <= 7.9 (8 trở xuống)

Hỗ trợ lọc theo range chương: --from v1_c10 --to v1_c50
"""

import re
import sys

import yaml

from cores.runtime_config import option, web_mode

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import os

REVIEW_YAML = "truyen/review.yaml"
OUTPUT_DIR = "truyen"


def parse_chapter_key(key):
    """Trích xuất (volume, chapter) từ key dạng v1_c27_s1."""
    m = re.match(r"v(\d+)_c(\d+)", key)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_range_arg(arg):
    """Parse chuỗi dạng 'v1_c10' thành (volume, chapter)."""
    if not arg:
        return None, None
    m = re.match(r"v(\d+)_c(\d+)", arg.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: thử parse số thuần túy làm chapter (mặc định volume 1)
    try:
        return 1, int(arg.strip())
    except ValueError:
        print(f"⚠️ Không hiểu range: '{arg}'. Dùng format v1_c10 hoặc số chương.")
        return None, None


def in_range(vol, ch, from_vc, to_vc):
    """Kiểm tra (vol, ch) có nằm trong [from_vc, to_vc] không."""
    if from_vc[0] is not None:
        if (vol, ch) < (from_vc[0], from_vc[1]):
            return False
    if to_vc[0] is not None:
        if (vol, ch) > (to_vc[0], to_vc[1]):
            return False
    return True


def split_review(review_path, from_vc, to_vc):
    """Đọc review.yaml và tách theo điểm."""
    with open(review_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        print("⚠️ File review.yaml rỗng!")
        return

    bucket_9 = {}  # 9.0 - 9.9
    bucket_8 = {}  # 8.0 - 8.9
    bucket_low = {}  # <= 7.9

    skipped = 0
    total = 0

    # Sắp xếp theo chapter
    sorted_keys = sorted(data.keys(), key=lambda k: parse_chapter_key(k))

    for key in sorted_keys:
        entry = data[key]
        vol, ch = parse_chapter_key(key)
        if vol is None:
            skipped += 1
            continue

        # Lọc range
        if not in_range(vol, ch, from_vc, to_vc):
            skipped += 1
            continue

        total += 1
        score = entry.get("score", 0)

        if 9 <= score < 10:
            bucket_9[key] = entry
        elif 8 <= score < 9:
            bucket_8[key] = entry
        elif score < 8:
            bucket_low[key] = entry
        # score == 10 không cần check → bỏ qua (hoàn hảo)

    return bucket_9, bucket_8, bucket_low, total, skipped


def save_bucket(bucket, filepath, label):
    """Lưu bucket ra file yaml."""
    if not bucket:
        print(f"  📭 {label}: 0 chương (không tạo file)")
        return

    # Sắp xếp theo chapter trước khi ghi
    sorted_bucket = dict(
        sorted(bucket.items(), key=lambda item: parse_chapter_key(item[0]))
    )

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(sorted_bucket, f, allow_unicode=True, sort_keys=False, width=200)

    print(f"  📄 {label}: {len(bucket)} chương → {filepath}")


def main():
    print("\n📊 Tách review.yaml theo điểm số")
    print("=" * 50)
    if web_mode():
        print("Đang dùng khoảng chương từ giao diện web.\n")
        from_input = str(option("from", "")).strip()
        to_input = str(option("to", "")).strip()
    else:
        print("Nhập range chương (Enter để bỏ qua = lấy tất cả)")
        print("Ví dụ: v1_c10  hoặc  v1_c100\n")
        from_input = input("  Từ chương (--from): ").strip()
        to_input = input("  Đến chương (--to):  ").strip()

    from_vc = parse_range_arg(from_input if from_input else None)
    to_vc = parse_range_arg(to_input if to_input else None)

    # Hiển thị range
    range_label = "tất cả"
    if from_vc[0] is not None or to_vc[0] is not None:
        f_str = f"v{from_vc[0]}_c{from_vc[1]}" if from_vc[0] else "đầu"
        t_str = f"v{to_vc[0]}_c{to_vc[1]}" if to_vc[0] else "cuối"
        range_label = f"{f_str} → {t_str}"

    print(f"\n📊 Range: {range_label}")
    print("=" * 50)

    bucket_9, bucket_8, bucket_low, total, skipped = split_review(
        REVIEW_YAML, from_vc, to_vc
    )

    # Đếm điểm 10 (hoàn hảo)
    perfect = total - len(bucket_9) - len(bucket_8) - len(bucket_low)

    print(f"\n📈 Tổng: {total} chương trong range")
    print(f"  ⭐ Điểm 10 (hoàn hảo): {perfect} chương")
    print(f"  🟢 Điểm 9-9.9: {len(bucket_9)} chương")
    print(f"  🟡 Điểm 8-8.9: {len(bucket_8)} chương")
    print(f"  🔴 Điểm ≤7.9:  {len(bucket_low)} chương")
    print()

    # Lưu file
    save_bucket(bucket_9, os.path.join(OUTPUT_DIR, "review_9.yaml"), "Điểm 9-9.9")
    save_bucket(bucket_8, os.path.join(OUTPUT_DIR, "review_8.yaml"), "Điểm 8-8.9")
    save_bucket(bucket_low, os.path.join(OUTPUT_DIR, "review_low.yaml"), "Điểm ≤7.9")

    print(f"\n✅ Hoàn tất!")


if __name__ == "__main__":
    main()
