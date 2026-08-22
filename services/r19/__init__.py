"""R19 settings and one-term translation services."""

from services.r19.repository import payload, project_enabled, save, task_options
from services.r19.service import R19Service
from services.r19.translation import translate_word

__all__ = [
    "R19Service",
    "payload",
    "project_enabled",
    "save",
    "task_options",
    "translate_word",
]
