"""One turn's negotiation phase — orchestrates pairwise private messaging.

Each round, every power gets one call to produce outgoing messages to
any subset of the other powers (or none). Within a round, messaging is
logically simultaneous — every agent sees the same `history` and does
not see messages produced THIS round until the next round. Across
rounds it is sequential: round 2+ sees the prior rounds' incoming
messages, so agents can react before committing orders. The runner
drives `negotiation_rounds` of these per movement phase and threads the
accumulated dialogue into order generation.
"""
from __future__ import annotations

from typing import Iterable

from diplomacy_a2a.agent import Agent, DialogueMessage, MessagesResult, StrategyNote
from diplomacy_a2a.game.state import GameState


def run_negotiation_round(
    agents: dict[str, Agent],
    state: GameState,
    history: list[DialogueMessage],
    *,
    powers: Iterable[str] | None = None,
    round_index: int = 1,
    total_rounds: int = 1,
    strategies_by_power: dict[str, list[StrategyNote]] | None = None,
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
        sh = (strategies_by_power or {}).get(power)
        result = agent.negotiate(
            state, history,
            round_index=round_index, total_rounds=total_rounds,
            strategy_history=sh,
        )
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
