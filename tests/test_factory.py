"""Routing tests for make_client — no network, no real API keys.

Neither the `anthropic` nor `openai` SDK calls out at construction time, so
dummy keys in the environment are enough to exercise the provider seam: which
model id maps to which LLMClient, and that the gateway path fails loudly when
its key is missing. This guards the seam before a sweep that mixes providers.
"""
from __future__ import annotations

import pytest

from diplomacy_a2a.config import GATEWAY_MODELS
from diplomacy_a2a.llm.anthropic_client import AnthropicClient, RunnerError
from diplomacy_a2a.llm.factory import make_client
from diplomacy_a2a.llm.gateway_client import GatewayClient


@pytest.fixture(autouse=True)
def _dummy_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both providers see a (fake) key so construction succeeds offline."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-dummy")


def test_claude_id_routes_to_anthropic() -> None:
    client = make_client("claude-sonnet-4-6")
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-sonnet-4-6"


@pytest.mark.parametrize("model", sorted(GATEWAY_MODELS.values()))
def test_gateway_ids_route_to_gateway(model: str) -> None:
    client = make_client(model)
    assert isinstance(client, GatewayClient)
    assert client.model == model


def test_unknown_provider_prefix_routes_to_gateway() -> None:
    # Anything not starting with "claude-" is assumed to be an OpenRouter id.
    client = make_client("some-future-vendor/model-x")
    assert isinstance(client, GatewayClient)


def test_routed_clients_satisfy_the_runner_contract() -> None:
    # The runner attaches an error logger via duck-typing (hasattr) and reads
    # `.model`; both impls must expose these regardless of provider.
    for model in ("claude-sonnet-4-6", GATEWAY_MODELS["deepseek"]):
        client = make_client(model)
        assert hasattr(client, "set_error_logger")
        assert hasattr(client, "chat")
        client.set_error_logger(None)  # must not raise


def test_kwargs_pass_through_to_implementation() -> None:
    client = make_client(GATEWAY_MODELS["deepseek"], max_retries=1)
    assert isinstance(client, GatewayClient)
    assert client._max_retries == 1


def test_gateway_without_key_raises_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RunnerError, match="OPENROUTER_API_KEY"):
        make_client(GATEWAY_MODELS["gemini"])
