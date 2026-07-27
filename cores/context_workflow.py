"""Shared chapter iteration for glossary generation engines."""

import os
import sys
import time

import yaml

from cores.context_utils import merge_context, save_yaml
from cores.dich_utils import load_md_chapter, scan_md_dir
from cores.runtime_config import bool_option, web_mode

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def run_context_generation(
    *,
    engine_name,
    setup_browser,
    close_browser,
    generate_glossary,
    raw_dir,
    context_file,
    batch_size,
):
    print(f"🚀 Tạo Glossary qua {engine_name}")
    print("=" * 50)
    if setup_browser and (
        not web_mode() or bool_option("open_browser_setup", True)
    ):
        setup_browser()

    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"❌ Không tìm thấy file .md nào trong {raw_dir}")
        return
    print(f"📚 Tìm thấy {len(raw_files)} chương raw")

    old_context = {}
    if os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8") as file:
            old_context = yaml.safe_load(file) or {}

    start_chapter = old_context.get("index", 0)
    if start_chapter < 0 or start_chapter >= len(raw_files):
        if start_chapter >= len(raw_files):
            print(
                f"✅ Đã xử lý hết tất cả {len(raw_files)} chương. Không cần chạy thêm."
            )
            return
        print(f"❌ Index không hợp lệ (index={start_chapter}), sẽ chạy từ đầu.")
        start_chapter = 0

    files_to_process = raw_files[start_chapter:]
    try:
        for offset in range(0, len(files_to_process), batch_size):
            batch_files = files_to_process[offset : offset + batch_size]
            batch = [load_md_chapter(path) for path in batch_files]
            batch_number = offset // batch_size + 1
            print(
                f"\n▶ Đang xử lý batch {batch_number} "
                f"({len(batch)} chương, từ chương {start_chapter + offset + 1})..."
            )

            new_glossary = generate_glossary(batch, old_context.get("glossary", ""))
            old_context = merge_context(old_context, new_glossary)
            old_context["index"] = start_chapter + offset + len(batch)
            save_yaml(old_context, context_file)
            print(
                f"✅ Đã cập nhật context.yaml sau batch {batch_number} "
                f"(index mới: {old_context['index']})"
            )
            print("⏳ Nghỉ 10 giây trước khi tiếp tục...")
            time.sleep(10)

        print("\n🎉 Hoàn tất!")
    except KeyboardInterrupt:
        print("\n⏹ Đã dừng bởi Ctrl + C")
    except SystemExit:
        pass
    finally:
        if close_browser:
            print("\n🔒 Đang đóng trình duyệt...")
            close_browser()
        print("✅ Đã hoàn tất!")
