"""Anthropic implementation of LLMClient.

Uses the Anthropic Python SDK directly. Prompt caching will be wired in
here — for Diplomacy, the rules + accumulated transcript are re-sent
every turn, so caching cuts those tokens to ~10% cost.
"""
from __future__ import annotations

from typing import Sequence

from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message


class AnthropicClient(LLMClient):
    def __init__(self, model: str) -> None:
        self.model = model
        # SDK client construction deferred until implementation.

    def chat(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
    ) -> ChatResult:
        raise NotImplementedError
