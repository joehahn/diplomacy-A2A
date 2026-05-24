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
    # Cache accounting (Anthropic-style; 0 for providers without caching).
    # Creation tokens are billed at a premium (write-to-cache); read tokens
    # at a deep discount. Tracking both lets us reason about cost per run.
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
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
