"""Gemini API provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse


class GeminiApiProvider(ProviderAdapter):
    id = "gemini-api"
    label = "Gemini API"

    def generate(self, request):
        documents = list(request.attachments)
        extra_parts = [
            {"text": f"## Reference file: {item['name']}\n\n{item['content']}"}
            for item in documents
        ]
        text = self._generate(
            request.prompt,
            model=request.model,
            thinking_level=request.thinking,
            as_chat_parts=bool(extra_parts),
            extra_parts=extra_parts or None,
            character_document=next(
                (item["content"] for item in documents if item["name"] == "characters.md"),
                None,
            ),
            pronoun_document=next(
                (item["content"] for item in documents if item["name"] == "pronouns_snapshot.json"),
                None,
            ),
            **request.options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
