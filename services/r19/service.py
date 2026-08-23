"""Application-level orchestration for R19 settings and term translation."""

from services.r19 import repository
from services.r19.translation import translate_word


class R19Service:
    def __init__(
        self,
        *,
        safe_project,
        words_path,
        config_path,
        default_words_path,
        default_model,
        default_context_chapters,
        default_prompt_prefix,
        active_translation,
        translation_guard,
        generate,
        log_call,
    ):
        self._safe_project = safe_project
        self._words_path = words_path
        self._config_path = config_path
        self._default_words_path = default_words_path
        self.default_model = default_model
        self.default_context_chapters = default_context_chapters
        self.default_prompt_prefix = default_prompt_prefix
        self._active_translation = active_translation
        self._translation_guard = translation_guard
        self._generate = generate
        self._log_call = log_call

    @staticmethod
    def _path(source):
        return source() if callable(source) else source

    def payload(self, project_name=""):
        return repository.payload(
            self._safe_project(project_name) if project_name else None,
            self._path(self._words_path),
            self._path(self._config_path),
            self._path(self._default_words_path),
            self.default_model,
            self.default_context_chapters,
            self.default_prompt_prefix,
        )

    def save(self, project_name, request):
        repository.save(
            self._safe_project(project_name),
            request,
            self._path(self._words_path),
            self._path(self._config_path),
            self.default_model,
            self.default_context_chapters,
            self.default_prompt_prefix,
        )
        return self.payload(project_name)

    def project_enabled(self, project_name):
        return bool(project_name) and repository.project_enabled(
            self._safe_project(project_name)
        )

    def enabled(self, project_name):
        return self.payload(project_name)["enabled"]

    def task_options(self, project_name):
        return repository.task_options(self.payload(project_name))

    def translate_word(self, project_name, request):
        source = str(request.get("source", "")).strip()
        project_path = self._safe_project(project_name)
        return translate_word(
            source,
            project_path,
            self._path(self._words_path),
            lambda: self.payload(project_name),
            self._active_translation,
            self._translation_guard,
            self._generate,
            lambda term, model, prompt, response, ok: self._log_call(
                project_path, term, model, prompt, response, ok
            ),
        )
