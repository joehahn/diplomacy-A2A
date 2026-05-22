"""LLM client abstraction (the seam) plus the Anthropic implementation.

External callers should depend on `LLMClient` from `client.py` only —
nothing else in the codebase imports the `anthropic` SDK directly.
Adding a second provider later means writing one new class that
satisfies `LLMClient`; no other code changes.
"""
from diplomacy_a2a.llm.client import LLMClient, Message, ChatResult

__all__ = ["LLMClient", "Message", "ChatResult"]
