"""ChatGPT Web V2: translate, polish, pronouns and review by batch."""

import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cores.chatgpt_web_v2 import run_chatgpt_v2_batch, stage_chatgpt_options
from cores.dich_gpt import (
    BRANCH,
    _build_batch_prompt,
    close_chatgpt_driver,
    get_chatgpt_driver,
    setup_chatgpt_browser,
)
from cores.dich_utils import (
    CONTEXT_YAML,
    NOVEL_TXT,
    RAW_DIR,
    TRANSLATED_DIR,
    generate_content_with_chatgpt,
)
from cores.runtime_config import bool_option, int_option, stop_requested, web_mode
from cores.translation_workflows import run_batch_translation, translate_batch_with_web


def translate_chapters(
    batch, start_chapter_number, context_text="", pronoun_context=""
):
    """The translation stage also starts from a fresh ChatGPT chat."""
    model, thinking = stage_chatgpt_options("translate")
    return translate_batch_with_web(
        batch,
        start_chapter_number,
        context_text,
        pronoun_context,
        novel_text_path=NOVEL_TXT,
        build_prompt=_build_batch_prompt,
        generate=lambda prompt: generate_content_with_chatgpt(
            prompt,
            chat_url="https://chatgpt.com/",
            chatgpt_model=model,
            chatgpt_thinking=thinking,
        ),
        reset_browser=lambda: get_chatgpt_driver().get("https://chatgpt.com/"),
        engine_name="ChatGPT Web V2",
        require_boundaries=True,
    )


def run_translation(
    raw_dir=RAW_DIR, translated_dir=TRANSLATED_DIR, context_path=CONTEXT_YAML
):
    return run_batch_translation(
        translate_chapters,
        int_option("batch_size", BRANCH, minimum=1),
        raw_dir,
        translated_dir,
        context_path,
        batch_postprocess=run_chatgpt_v2_batch,
    )


if __name__ == "__main__":
    try:
        print("🚀 ChatGPT Web V2 — toàn bộ pipeline chạy theo batch")
        if not web_mode() or bool_option("open_browser_setup", True):
            setup_chatgpt_browser()
        batch_runs = int_option("batch_runs", 1, minimum=0)
        completed = 0
        while batch_runs == 0 or completed < batch_runs:
            if stop_requested():
                print("Đã dừng trước khi nhận batch tiếp theo.")
                break
            count = run_translation()
            if not count:
                break
            completed += 1
        print(f"✅ Đã xử lý {completed} batch ChatGPT Web V2.")
    finally:
        close_chatgpt_driver()
