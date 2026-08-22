"""Stage-based 1.0 entrypoint backed by verified provider adapters."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cores.config.runtime import task_config
from cores.translation.orchestration import main as run_translation
from providers.registry import pipeline_config


def main():
    config = pipeline_config(task_config())
    os.environ["NOVEL_WEB_CONFIG"] = __import__("json").dumps(config, ensure_ascii=False)
    task_config.cache_clear()
    print("Pipeline 1.0:", " | ".join(
        f"{stage}={provider}" for stage, provider in config["stage_providers"].items()
    ))
    run_translation()


if __name__ == "__main__":
    main()
