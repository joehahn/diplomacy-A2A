"""make_client — map a model id to the right LLMClient implementation.

Routing is by model-id shape: Anthropic's own ids start with `claude-`;
everything else is assumed to be an OpenRouter `provider/model` id
(e.g. `deepseek/deepseek-v4-flash`, `google/gemini-3-flash`) and goes
through the gateway. This is the single place that knows about more than
one provider, so the call sites stay provider-agnostic.

Imports are lazy so a normal Anthropic-only run never imports `openai`
(and vice versa).
"""
from __future__ import annotations

from diplomacy_a2a.llm.client import LLMClient


def make_client(model: str, **kwargs) -> LLMClient:
    if model.startswith("claude-"):
        from diplomacy_a2a.llm.anthropic_client import AnthropicClient

        return AnthropicClient(model=model, **kwargs)
    from diplomacy_a2a.llm.gateway_client import GatewayClient

    return GatewayClient(model=model, **kwargs)
