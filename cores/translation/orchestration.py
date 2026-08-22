"""Run the configured stage translation pipeline."""

import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cores.config import CONTEXT_JSON, RAW_DIR, TRANSLATED_DIR
from cores.postprocess import runtime as postprocess_runtime
from cores.config.runtime import bool_option, chapter_limit, stop_requested, web_mode
from cores.translation.runner import run_single_translation
from cores.translation.stage import provider, translate_chapter


def run_requested_chapters(limit, run_chapter):
    processed = 0
    while limit is None or processed < limit:
        if stop_requested():
            break
        count = run_chapter() or 0
        if not count:
            break
        processed += count
    return processed


def main():
    providers = {
        provider(stage) for stage in ("translate", "polish", "pronouns", "review")
    }
    should_setup = not web_mode() or bool_option("open_browser_setup", True)
    if should_setup:
        for provider_id in providers:
            postprocess_runtime.setup_browser(provider_id)
    try:
        limit = chapter_limit() if web_mode() else None

        def run_chapter():
            count = run_single_translation(
                translate_chapter,
                RAW_DIR,
                TRANSLATED_DIR,
                CONTEXT_JSON,
            )
            if count:
                time.sleep(1)
            return count

        run_requested_chapters(limit, run_chapter)
    finally:
        postprocess_runtime.close_browsers()


if __name__ == "__main__":
    main()
