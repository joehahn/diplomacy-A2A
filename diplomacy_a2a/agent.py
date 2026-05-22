"""Agent = persona (system prompt) + LLMClient + conversation memory.

One Agent instance per power per game. Responsible for: receiving
incoming messages from other powers, producing outgoing messages,
and (at end of negotiation phase) emitting the final order set for
the turn.
"""
from __future__ import annotations


class Agent:
    def __init__(self) -> None:
        raise NotImplementedError
