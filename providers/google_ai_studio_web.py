"""Google AI Studio Web provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse


class GoogleAiStudioWebProvider(ProviderAdapter):
    id = "google-ai-studio-web"
    label = "Google AI Studio Web"

    def generate(self, request):
        text = self._generate(
            request.prompt,
            ai_studio_model=request.model,
            ai_studio_thinking=request.thinking,
            ai_studio_references=request.attachments,
            **request.options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
