"""Gemini Web provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse, prompt_with_attachments


class GeminiWebProvider(ProviderAdapter):
    id = "gemini-web"
    label = "Gemini Web"

    def generate(self, request):
        prompt = request.prompt
        if request.stage != "translate":
            prompt = prompt_with_attachments(prompt, request.attachments)
        text = self._generate(
            prompt,
            web_model=request.model,
            thinking_level=request.thinking,
            **request.options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
