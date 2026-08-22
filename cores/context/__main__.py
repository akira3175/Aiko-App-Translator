"""Generate project Context through the configured provider."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cores.config import CONTEXT_JSON, RAW_DIR
from cores.context.generation import (
    browser_lifecycle,
    context_model_and_thinking,
    context_provider,
    generate_glossary,
)
from cores.context.workflow import run_context_generation
from cores.config.runtime import int_option


def main():
    provider = context_provider()
    model, _thinking = context_model_and_thinking(provider)
    if model.strip().lower() in {"", "none"}:
        print("Bỏ qua tạo Context vì chưa cấu hình model.")
        return
    setup_browser, close_browser = browser_lifecycle(provider)
    return run_context_generation(
        engine_name=provider,
        setup_browser=setup_browser,
        close_browser=close_browser,
        generate_glossary=generate_glossary,
        raw_dir=RAW_DIR,
        context_file=CONTEXT_JSON,
        batch_size=int_option("batch_size", 30, minimum=1),
    )


if __name__ == "__main__":
    main()
