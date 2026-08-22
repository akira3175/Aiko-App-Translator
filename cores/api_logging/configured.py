"""Project-configured API call logging."""

import threading

from cores.api_logging.api_calls import log_api_call
from cores.config import LOG_DIR


_lock = threading.Lock()


def log_project_api_call(
    chapter_id,
    step,
    model,
    prompt,
    response,
    ok=True,
    attachments=None,
):
    return log_api_call(
        LOG_DIR,
        _lock,
        chapter_id,
        step,
        model,
        prompt,
        response,
        ok,
        attachments,
    )
