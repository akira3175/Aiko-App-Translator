"""Orchestration for the legacy post-translation pipeline."""


def update_final_pronouns(
    runtime, chapter, chapter_number, pronouns_file,
    *, polished_content=None, pronoun_output=None,
):
    """Use polish metadata only while it still describes the final prose."""
    if not runtime.enabled("pronouns"):
        print("[PIPELINE] Bỏ qua xuất xưng hô vì công đoạn đã tắt.")
        return
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    content = chapter.get("translation", "")
    if pronoun_output and content == polished_content:
        print("[PIPELINE] Lưu xưng hô từ kết quả hiệu đính...")
        return runtime.apply_pronoun_payload(
            chapter_id, chapter_number, pronoun_output, pronouns_file,
        )
    reason = "bản dịch đã thay đổi" if polished_content is not None and content != polished_content else "chưa có JSON xưng hô hợp lệ"
    print(f"[PIPELINE] Trích xuất xưng hô từ bản cuối ({reason})...")
    return runtime.update_pronoun_memory(
        chapter_id, chapter_number, content, pronouns_file,
        source_text=chapter.get("content", ""),
    )


def run_post_translation_pipeline(
    runtime,
    chapter,
    chapter_number,
    context_text,
    pronoun_context,
    pronouns_file,
):
    """
    Wrapper chạy toàn bộ pipeline hậu dịch.

    Bước 1 (tuần tự): hiệu đính bằng provider đã chọn.
    Bước 2 (tuần tự): xét sót ngôn ngữ bằng cùng provider hiệu đính.
    Bước 3 (tuần tự): lưu xưng hô hiệu đính hoặc dùng provider xưng hô dự phòng.
    Review nền được xếp riêng sau hàm này để mọi engine dùng chung một worker.

    Trả về (title, content) sau khi bước 1-3 hoàn tất.
    """
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    print(f"\n{'─' * 55}")
    print(f"[PIPELINE] Bắt đầu hậu xử lý chương {chapter_number} ({chapter_id})")
    print(f"{'─' * 55}")

    title_fixed = chapter.get("title_translation", "")
    content_fixed = chapter.get("translation", "")
    content_polished = None
    pronoun_output = {}
    if runtime.enabled("polish"):
        # ── Bước 1: Biên tập trau chuốt + chỉnh xưng hô ──
        print(f"[PIPELINE] Bước 1 — Biên tập trau chuốt...")
        title_polished, content_polished = runtime.polish_translation(
            chapter,
            chapter_number,
            context_text,
            pronoun_context,
            pronouns_file=pronouns_file,
            pronoun_output=pronoun_output,
        )
        chapter["title_translation"] = title_polished
        chapter["translation"] = content_polished

        # ── Bước 2: Xét sót ngôn ngữ ──
        print(f"[PIPELINE] Bước 2 — Xét sót ngôn ngữ...")
        title_fixed, content_fixed = runtime.fix_translation(
            chapter, chapter_number, context_text, pronoun_context
        )
    else:
        print("[PIPELINE] Bỏ qua hậu dịch vì chưa cấu hình model.")
    chapter["title_translation"] = title_fixed
    chapter["translation"] = content_fixed

    # ── Bước 3: Cập nhật bộ nhớ xưng hô ──
    update_final_pronouns(
        runtime, chapter, chapter_number, pronouns_file,
        polished_content=content_polished, pronoun_output=pronoun_output,
    )

    print(f"[PIPELINE] ✅ Hoàn tất hậu xử lý chương {chapter_number}")
    return title_fixed, content_fixed
