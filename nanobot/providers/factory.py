"""Provider factory shared by CLI and AGUI.

Keep all "build provider from Config" logic here so the web API can
hot-reload providers after config updates without importing CLI code.
"""

from __future__ import annotations

from nanobot.config.schema import Config


def make_provider(config: Config):
    """Create the appropriate LLM provider from config.

    Raises:
        ValueError: when required provider config is missing.
    """
    from nanobot.providers.azure_openai_provider import AzureOpenAIProvider
    from nanobot.providers.base import GenerationSettings
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    # Important: do NOT implicitly reuse tools.web.proxy for LLM traffic.
    # Users often set tools.web.proxy to reach external websites (search/fetch),
    # but routing LLM calls through that proxy can cause MITM, blocked TLS, or
    # unexpected upstream behavior. LLM proxy must be explicitly configured per
    # provider via providers.<name>.proxy.
    llm_proxy = (p.proxy if p else None) or None
    ssl_verify = config.tools.web.ssl_verify

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        provider = OpenAICodexProvider(default_model=model)

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    elif provider_name == "custom":
        from nanobot.providers.custom_provider import CustomProvider

        provider = CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            proxy=llm_proxy,
            ssl_verify=ssl_verify,
        )

    # Azure OpenAI: direct Azure OpenAI endpoint with deployment name
    elif provider_name == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            raise ValueError("Azure OpenAI requires providers.azure_openai.api_key and api_base")
        provider = AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )

    # OpenVINO Model Server: direct OpenAI-compatible endpoint at /v3
    elif provider_name == "ovms":
        from nanobot.providers.custom_provider import CustomProvider

        provider = CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v3",
            default_model=model,
            proxy=llm_proxy,
            ssl_verify=ssl_verify,
        )

    else:
        from nanobot.providers.litellm_provider import LiteLLMProvider
        from nanobot.providers.registry import find_by_name

        spec = find_by_name(provider_name or "")
        has_key = bool(p and p.api_key)
        if (
            not model.startswith("bedrock/")
            and not has_key
            and not (spec and (spec.is_oauth or spec.is_local))
        ):
            raise ValueError("No API key configured for selected model/provider")

        provider = LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            provider_name=provider_name,
            proxy=llm_proxy,
            ssl_verify=ssl_verify,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider

