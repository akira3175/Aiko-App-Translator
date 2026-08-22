"""Concurrent execution for full-novel review requests."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from cores.full_review.service import (
    build_review_prompt,
    call_review_api,
    process_review_result,
)
from cores.full_review.storage import save_manual_check, save_review
from cores.gemini import switch_api_key


def review_worker_count(provider, workers):
    return 1 if provider in {"gemini-web", "chatgpt-web"} else workers * 3


def run_review_items(
    review_items,
    context_text,
    review_store,
    manual_list,
    *,
    provider,
    batch_size,
    workers,
    sleep_between,
    review_path,
    manual_path,
):
    """Run all prepared items and return the reviewed and error counts."""
    total_items = len(review_items)
    num_batches = (total_items + batch_size - 1) // batch_size
    reviewed = 0
    errors = 0
    save_counter = 0
    result_lock = threading.Lock()

    def review_one(global_order, item):
        chapter_id, chapter_number, raw_title, raw_content, title, content = item
        prompt = build_review_prompt(
            chapter_id,
            chapter_number,
            raw_title,
            raw_content,
            title,
            content,
            context_text,
        )
        result = call_review_api(prompt, provider)
        return global_order, chapter_id, chapter_number, result

    def on_done(future):
        nonlocal reviewed, errors, save_counter
        try:
            _order, chapter_id, chapter_number, result = future.result()
            with result_lock:
                process_review_result(
                    chapter_id, chapter_number, result, review_store, manual_list
                )
                reviewed += 1
                save_counter += 1
                if save_counter >= batch_size:
                    save_review(review_store, review_path)
                    save_manual_check(manual_list, manual_path)
                    print(f"  💾 Auto-save ({reviewed}/{total_items} reviewed)")
                    save_counter = 0
        except Exception as error:
            with result_lock:
                errors += 1
            print(f"  ❌ Exception: {error}")

    futures = []
    max_workers = review_worker_count(provider, workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch_index in range(num_batches):
            batch_start = batch_index * batch_size
            batch_end = min(batch_start + batch_size, total_items)
            batch = review_items[batch_start:batch_end]
            for local_index, item in enumerate(batch):
                future = executor.submit(review_one, batch_start + local_index, item)
                future.add_done_callback(on_done)
                futures.append(future)
            print(
                f"  🚀 Đã gửi batch {batch_index + 1}/{num_batches} "
                f"({len(batch)} chương: {batch_start + 1}~{batch_end})"
            )
            if batch_index < num_batches - 1:
                time.sleep(sleep_between)
                if provider == "gemini-api":
                    switch_api_key()
        print(f"\n  ⏳ Đã gửi hết {total_items} request, đang chờ kết quả còn lại...")
        wait(futures)

    save_review(review_store, review_path)
    save_manual_check(manual_list, manual_path)
    return reviewed, errors
