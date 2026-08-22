"""Provider contracts used by the stage-based 1.0 pipeline."""

from dataclasses import dataclass, field
from typing import Any, Callable


STAGES = ("translate", "polish", "pronouns", "review", "glossary", "characters")


@dataclass(frozen=True)
class ProviderCapabilities:
    stages: tuple[str, ...]
    browser: bool = False
    batch: bool = False
    attachments: bool = False
    thinking: bool = False
    streaming: bool = False


@dataclass(frozen=True)
class ProviderRequest:
    stage: str
    prompt: str
    model: str
    thinking: str | None = None
    attachments: tuple[dict, ...] = ()
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    provider: str
    model: str


class ProviderAdapter:
    id = ""
    label = ""
    capabilities = ProviderCapabilities(())

    def validate_settings(self, settings):
        return dict(settings or {})

    def test_connection(self):
        raise NotImplementedError

    def __init__(self, generate: Callable):
        self._generate = generate

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError

    def cancel(self):
        return None


def prompt_with_attachments(prompt, attachments):
    blocks = [prompt]
    for document in attachments:
        blocks.append(f"## Reference file: {document['name']}\n\n{document['content']}")
    return "\n\n".join(blocks)
