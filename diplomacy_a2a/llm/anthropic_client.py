"""Anthropic implementation of LLMClient.

Wraps `anthropic.Anthropic` and exposes our provider-neutral `chat()`
interface. Adds prompt caching on the system prompt — for Diplomacy
the rules + persona + power assignment are re-sent on every call, so
caching cuts those tokens to ~10% of normal price after the first
write-to-cache.

API key is read from the ANTHROPIC_API_KEY environment variable by the
SDK (we do not handle it directly). Callers are expected to have run
`dotenv.load_dotenv()` before instantiating this client.
"""
from __future__ import annotations

from typing import Sequence

from anthropic import Anthropic

from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message


class AnthropicClient(LLMClient):
    def __init__(self, model: str) -> None:
        self.model = model
        self._client = Anthropic()

    def chat(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        temperature: float,
    ) -> ChatResult:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return ChatResult(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            raw=response,
        )
