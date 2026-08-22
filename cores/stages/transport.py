"""Provider-independent generation for pipeline stages."""

from providers import ProviderRequest, create_provider


def generate_for_stage(
    provider_id,
    stage,
    prompt,
    model,
    thinking,
    transports,
    attachments=(),
    options=None,
):
    try:
        transport = transports[provider_id]
    except KeyError as error:
        raise ValueError(f"Chưa cấu hình transport cho provider {provider_id}") from error
    provider = create_provider(provider_id, transport, stage)
    request = ProviderRequest(
        stage=stage,
        prompt=prompt,
        model=model,
        thinking=thinking,
        attachments=tuple(attachments or ()),
        options=dict(options or {}),
    )
    return provider.generate(request)
