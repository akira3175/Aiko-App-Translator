"""Antigravity CLI provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse


class AntigravityCliProvider(ProviderAdapter):
    id = "antigravity-cli"
    label = "Antigravity CLI"

    def generate(self, request):
        text = self._generate(
            request.prompt,
            model=request.model,
            reasoning_effort=request.thinking,
            stage=request.stage,
            documents=list(request.attachments) or None,
            **request.options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
