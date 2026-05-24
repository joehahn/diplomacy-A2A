"""One turn's negotiation phase — orchestrates pairwise private messaging.

For v1 we run a single negotiation round per movement phase: every power
gets one call to produce outgoing messages to any subset of the other
powers. The messages are collected and threaded into the next call
(order generation) as dialogue history.

Multi-round negotiation (where round 2+ sees round 1's incoming
messages) is a future extension — the shape here supports it
naturally.
"""
from __future__ import annotations

from typing import Iterable

from diplomacy_a2a.agent import Agent, DialogueMessage, MessagesResult
from diplomacy_a2a.game.state import GameState


def run_negotiation_round(
    agents: dict[str, Agent],
    state: GameState,
    history: list[DialogueMessage],
    *,
    powers: Iterable[str] | None = None,
) -> tuple[list[DialogueMessage], dict[str, MessagesResult]]:
    """Run one round of messaging across the given powers.

    Each agent produces outgoing messages keyed by recipient power.
    Returns (new_messages_this_round, per_power_chat_results) so the
    runner can log everything and track token costs.

    Messaging is logically simultaneous: each agent's view of `history`
    is the same — they don't see messages produced THIS round by other
    agents until the next round (or until order generation).
    """
    short_phase = state.short_phase
    powers_iter = list(powers) if powers is not None else list(agents.keys())
    new_messages: list[DialogueMessage] = []
    results: dict[str, MessagesResult] = {}

    for power in powers_iter:
        agent = agents[power]
        result = agent.negotiate(state, history)
        results[power] = result
        for recipient, text in result.messages.items():
            new_messages.append(
                DialogueMessage(
                    phase=short_phase,
                    sender=power,
                    recipient=recipient,
                    text=text,
                )
            )

    return new_messages, results
