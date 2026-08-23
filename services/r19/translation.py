"""Translate one R19 term from the settings page."""

from cores.r19 import storage
from cores.r19.translation import request_word_translation


def translate_word(
    source,
    project_path,
    words_path,
    current_payload,
    active_translation,
    translation_guard,
    generate,
    logger,
):
    if not source or len(source) > 200 or "\n" in source or "\r" in source:
        raise ValueError("Từ/cụm R19 không hợp lệ")
    if not project_path.is_dir():
        raise ValueError("Truyện không tồn tại")

    terms, translations = storage.load_word_mappings(words_path)
    if source.casefold() not in {term.casefold() for term in terms}:
        raise ValueError("Hãy lưu dòng R19 trước khi dịch")
    cached = translations.get(source.casefold())
    if cached:
        return {**current_payload(), "source": source, "translation": cached, "cached": True}
    model = current_payload()["model"]
    with translation_guard:
        if active_translation():
            raise ValueError("Hãy chờ tác vụ dịch hiện tại kết thúc")
        translation = request_word_translation(
            source,
            "manager",
            model,
            generate=lambda request_prompt: generate(request_prompt, model),
            logger=lambda request_prompt, response, ok: logger(
                source, model, request_prompt, response, ok
            ),
        )
        storage.save_word_translation(source, translation, words_path)
    return {
        **current_payload(),
        "source": source,
        "translation": translation,
        "cached": False,
    }
