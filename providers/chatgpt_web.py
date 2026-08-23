"""ChatGPT Web provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse, prompt_with_attachments


class ChatGptWebProvider(ProviderAdapter):
    id = "chatgpt-web"
    label = "ChatGPT Web"

    def generate(self, request):
        options = dict(request.options)
        prompt = request.prompt
        if request.stage != "translate":
            prompt = prompt_with_attachments(prompt, request.attachments)
        text = self._generate(
            prompt,
            chatgpt_model=request.model,
            chatgpt_thinking=request.thinking,
            **options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
