"""Small control events consumed by the web job runner."""

import json
import os


def emit_job_event(event_type, **payload):
    if os.environ.get("NOVEL_WEB_MODE") != "1":
        return
    event = {"type": event_type, **payload}
    print(
        "@@NOVEL_STREAM@@"
        + json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
