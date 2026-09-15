"""Review, context, character, pronoun, and manual translation HTTP routes."""

import json
import subprocess
from dataclasses import dataclass
from http import HTTPStatus

@dataclass(frozen=True)
class ContentRoutes:
    reviews: object
    context: object
    characters: object
    pronouns: object
    prepare_manual_prompt: object
    translate_selection: object

    def handle_get(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == "/api/reviews":
            return self._json_call(
                handler,
                lambda: self.reviews.payload(
                    project, query.get("source", [""])[0]
                ),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/context":
            return self._json_call(
                handler,
                lambda: self.context.data(project),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/characters":
            return self._json_call(
                handler,
                lambda: self.characters.data(project),
                (ValueError, OSError),
            )
        if path == "/api/pronouns":
            return self._json_call(
                handler,
                lambda: self.pronouns.data(project),
                (ValueError, OSError, json.JSONDecodeError),
            )
        return False

    def handle_post(self, handler, path, query):
        project = query.get("project", [""])[0]
        if path == '/api/context/prompt-preview':
            return self._json_call(handler, lambda: self.context.preview_prompt(project, handler.body()),
                                   (ValueError, OSError, TypeError, json.JSONDecodeError))
        if path == "/api/context":
            return self._json_call(
                handler,
                lambda: self.context.save(project, handler.body()),
                (Exception,),
            )
        if path == "/api/characters":
            return self._json_call(
                handler,
                lambda: self.characters.save(project, handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/pronouns":
            return self._json_call(
                handler,
                lambda: self.pronouns.save(project, handler.body()),
                (ValueError, OSError, json.JSONDecodeError),
            )
        if path == "/api/manual-prompt":
            try:
                handler.json_response(self.prepare_manual_prompt(project))
            except (
                ValueError,
                OSError,
                json.JSONDecodeError,
                subprocess.TimeoutExpired,
            ) as exc:
                message = (
                    "Tạo prompt quá thời gian cho phép"
                    if isinstance(exc, subprocess.TimeoutExpired)
                    else str(exc)
                )
                handler.json_response({"error": message}, HTTPStatus.BAD_REQUEST)
            return True
        if path == "/api/translate-selection":
            return self._json_call(
                handler,
                lambda: self.translate_selection(
                    str(handler.body().get("text", ""))
                ),
                (ValueError, OSError, json.JSONDecodeError),
            )
        return False

    @staticmethod
    def _json_call(handler, action, errors):
        try:
            handler.json_response(action())
        except errors as exc:
            handler.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True
