"""Agent = power + persona + LLMClient.

One Agent per power per game. v1 responsibility: given the current
GameState, produce a list of orders for this power's units. Validation
(do the orders match the adjudicator's legal-move list?) and
submission to the state are deliberately left to orchestration so the
Agent stays single-purpose.

The system prompt is assembled once and reused on every call within
the game — same byte sequence → Anthropic prompt caching engages on
the second call onward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from diplomacy_a2a.game.state import GameState
from diplomacy_a2a.game.view import render_for_power
from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message

_RULES_PATH = Path(__file__).parent / "game" / "rules.md"


def _load_default_rules() -> str:
    return _RULES_PATH.read_text()


@dataclass(frozen=True)
class OrderResult:
    """What Agent.submit_orders returns. Orchestration decides what to do with it."""

    orders: list[str]
    chat: ChatResult


class Agent:
    def __init__(
        self,
        *,
        power: str,
        persona: str,
        client: LLMClient,
        rules: str | None = None,
    ) -> None:
        self.power = power
        self.persona = persona
        self.client = client
        self.rules = rules if rules is not None else _load_default_rules()
        self._system = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return (
            f"{self.rules}\n\n"
            f"You are playing as {self.power} in a game of Diplomacy.\n\n"
            f"## Your persona\n{self.persona}\n\n"
            "## Output format\n"
            "When asked to submit orders, reason briefly (one short paragraph) about your\n"
            "strategy this phase, then emit exactly one order for each of your units, using\n"
            "the legal-order strings EXACTLY as shown in the menu. Anything not in the menu\n"
            "will be rejected.\n\n"
            "End your response with a section beginning with `ORDERS:` on its own line,\n"
            "followed by one order per line, like:\n\n"
            "ORDERS:\n"
            "A PAR - BUR\n"
            "A MAR - SPA\n"
            "F BRE - MAO\n\n"
            "Do not include any text after the ORDERS: section."
        )

    def submit_orders(
        self,
        state: GameState,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> OrderResult:
        view = render_for_power(state, self.power)
        user_msg = view + f"\n\nIt is your turn. Submit your orders for {state.phase}."
        chat = self.client.chat(
            system=self._system,
            messages=[Message(role="user", content=user_msg)],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return OrderResult(orders=parse_orders(chat.text), chat=chat)


def parse_orders(text: str) -> list[str]:
    """Extract orders from an LLM response.

    Expects an `ORDERS:` section at the end; takes the lines that follow,
    strips markdown decoration (backticks, leading dashes/numbers), and
    returns the non-empty results in order.
    """
    if "ORDERS:" not in text:
        return []
    _, tail = text.rsplit("ORDERS:", 1)
    out: list[str] = []
    for line in tail.strip().splitlines():
        s = line.strip()
        # Strip leading list markers and trailing backticks/punctuation
        s = s.lstrip("-*0123456789. ").strip()
        s = s.strip("`").strip()
        if s:
            out.append(s)
    return out


def validate_orders(state: GameState, power: str, orders: list[str]) -> tuple[list[str], list[str]]:
    """Return (valid, invalid) — partitioning the proposed orders against the legal-moves list."""
    legal_set: set[str] = set()
    for opts in state.legal_orders(power).values():
        legal_set.update(opts)
    valid, invalid = [], []
    for o in orders:
        (valid if o in legal_set else invalid).append(o)
    return valid, invalid
