"""Generate project character profiles through the configured provider."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from cores.characters import run_character_generation
from cores.config import CHARACTERS_MD, CONTEXT_JSON, RAW_DIR
from cores.config.runtime import bool_option, option, web_mode
from cores.stages import browser_lifecycle, stage_model_and_thinking, stage_provider

CHAR_INDEX_FILE = os.path.join(os.path.dirname(RAW_DIR), "project_state.json")


def main():
    provider = stage_provider("characters", get_option=option)
    model, _thinking = stage_model_and_thinking(
        "characters", provider, get_option=option
    )
    setup_browser, close_browser = browser_lifecycle(provider)
    should_setup = not web_mode() or bool_option("open_browser_setup", True)
    if setup_browser and should_setup:
        setup_browser()
    try:
        return run_character_generation(
            raw_dir=RAW_DIR,
            context_path=CONTEXT_JSON,
            characters_path=CHARACTERS_MD,
            state_path=CHAR_INDEX_FILE,
            provider=provider,
            model=model,
        )
    finally:
        if close_browser:
            close_browser()


if __name__ == "__main__":
    main()
