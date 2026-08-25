"""Concurrent execution for full-novel review requests."""

import time
from concurrent.futures import ThreadPoolExecutor, wait

from cores.full_review.service import (
    build_review_prompt,
    call_review_api,
    process_review_result,
)
from cores.full_review.storage import save_manual_check, save_review
from cores.stages import build_reference_documents
from cores.translation.prompts import with_character_document_instruction


def review_worker_count(provider, workers):
    return 1 if provider in {"gemini-web", "chatgpt-web"} else workers


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
        documents = build_reference_documents(
            {
                "title": raw_title,
                "content": raw_content,
                "title_translation": title,
                "translation": content,
            },
            include_translation=True,
        )
        if any(document["name"] == "characters.md" for document in documents):
            prompt = with_character_document_instruction(prompt)
        result = call_review_api(prompt, provider, documents)
        return global_order, chapter_id, chapter_number, result

    def collect_result(future):
        nonlocal reviewed, errors
        try:
            _order, chapter_id, chapter_number, result = future.result()
            process_review_result(
                chapter_id, chapter_number, result, review_store, manual_list
            )
            reviewed += 1
        except Exception as error:
            errors += 1
            print(f"  ❌ Exception: {error}")

    max_workers = review_worker_count(provider, workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch_index in range(num_batches):
            batch_start = batch_index * batch_size
            batch_end = min(batch_start + batch_size, total_items)
            batch = review_items[batch_start:batch_end]
            batch_futures = [
                executor.submit(review_one, batch_start + local_index, item)
                for local_index, item in enumerate(batch)
            ]
            print(
                f"  🚀 Đã gửi batch {batch_index + 1}/{num_batches} "
                f"({len(batch)} chương: {batch_start + 1}~{batch_end})"
            )
            wait(batch_futures)
            for future in batch_futures:
                collect_result(future)
            save_review(review_store, review_path)
            save_manual_check(manual_list, manual_path)
            print(
                f"  💾 Hoàn tất batch {batch_index + 1}/{num_batches} "
                f"({reviewed}/{total_items} reviewed)"
            )
            if batch_index < num_batches - 1:
                time.sleep(sleep_between)

    save_review(review_store, review_path)
    save_manual_check(manual_list, manual_path)
    return reviewed, errors
