"""LLMClient protocol — the architectural seam for swapping providers.

v1 ships a single AnthropicClient implementation in `anthropic_client.py`.
To add a second provider (OpenAI, LiteLLM, Grok, etc.), write a new
class that satisfies LLMClient. Nothing else in the codebase needs to
change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Message:
    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0  # provider-specific; 0 if unsupported
    raw: object = field(default=None, repr=False)  # provider-native response, for debugging


class LLMClient(Protocol):
    """Minimal chat interface. All providers must satisfy this."""

    def chat(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
    ) -> ChatResult:
        ...
