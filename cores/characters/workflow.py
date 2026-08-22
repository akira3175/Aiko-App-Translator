"""Incremental character-profile workflow."""

import time

from cores.chapters.files import load_md_chapter, scan_md_dir
from cores.characters.generation import request_character_block
from cores.characters.parser import merge_characters
from cores.characters.prompt import build_character_prompt
from cores.characters.storage import (
    build_document,
    document_body,
    load_glossary,
    load_index,
    load_markdown,
    save_index,
    save_markdown,
)
from cores.config.runtime import int_option, option, stop_requested


def run_character_generation(
    *, raw_dir, context_path, characters_path, state_path, provider, model
):
    batch_size = min(int_option("character_batch_size", 10, minimum=1), 100)
    max_retries = min(int_option("character_retries", 3, minimum=1), 10)
    print(f"Phân tích thông tin nhân vật qua {provider}")
    print("=" * 50)
    print(f"Model: {model}")
    print(f"Batch size: {batch_size} chương/batch\n")

    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"Không tìm thấy file .md nào trong {raw_dir}")
        return

    total_files = len(raw_files)
    requested_start = int_option("character_start", 1, minimum=1) - 1
    requested_end = int_option("character_end", total_files, minimum=1)
    force = str(option("character_force", "false")).lower() in {
        "1", "true", "yes", "on"
    }
    saved_index = load_index(state_path)
    start_index = requested_start if force else max(saved_index, requested_start)
    end_index = min(total_files, requested_end)
    if start_index >= end_index:
        print(f"Đã phân tích hết {total_files} chương. Không cần chạy thêm.")
        print("Chọn 'Chạy lại phạm vi' nếu muốn phân tích lại.")
        return

    files = raw_files[start_index:end_index]
    body = document_body(load_markdown(characters_path))
    glossary = load_glossary(context_path)
    print(
        f"Tổng chương raw: {total_files} | Sẽ xử lý: {len(files)} "
        f"(từ index {start_index + 1})."
    )
    print(
        f"Đã tải glossary ({len(glossary.splitlines())} mục)"
        if glossary
        else "Không tìm thấy glossary"
    )

    try:
        for offset in range(0, len(files), batch_size):
            if stop_requested():
                print("Đã dừng trước batch tiếp theo.")
                return
            batch_files = files[offset : offset + batch_size]
            batch = [load_md_chapter(path) for path in batch_files]
            first = start_index + offset + 1
            last = start_index + offset + len(batch)
            print(f"\n[Batch {offset // batch_size + 1}] Chương {first} -> {last} ({len(batch)} chương)...")

            prompt = build_character_prompt(batch, body, glossary)
            new_block = request_character_block(
                prompt, provider=provider, max_retries=max_retries
            )
            body = merge_characters(body, new_block)
            save_markdown(build_document(body), characters_path)

            new_index = start_index + offset + len(batch)
            save_index(max(saved_index, new_index), state_path)
            print(f"   Đã lưu tiến độ: index = {new_index} / {total_files}")
            if offset + batch_size < len(files):
                print("Nghỉ 5 giây trước batch tiếp theo...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("\nĐã dừng bởi Ctrl+C. Tiến độ đã được lưu.")

    print(f"\nXong! File nhân vật: {characters_path}")
    print(f"Tổng chương đã phân tích: {min(start_index + len(files), total_files)} / {total_files}")
