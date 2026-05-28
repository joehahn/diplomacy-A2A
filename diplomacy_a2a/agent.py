"""Agent = power + persona + LLMClient.

One Agent per power per game. Responsibilities:
- `negotiate(state, history)` — produce private outgoing messages to other powers
- `submit_orders(state, dialogue=...)` — produce orders, optionally informed by this phase's dialogue

Validation, submission, and orchestration across multiple agents stay
outside this class so it remains single-purpose.

The system prompt is assembled once and reused on every call within the
game — same byte sequence → Anthropic prompt caching engages on every
call after the first per agent. The prompt covers both output formats
(MESSAGES + ORDERS) so the same cache entry serves both call types.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from diplomacy_a2a.game.state import GameState, POWERS
from diplomacy_a2a.game.view import render_for_power
from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message

_RULES_PATH = Path(__file__).parent / "game" / "rules.md"


def _load_default_rules() -> str:
    return _RULES_PATH.read_text()


@dataclass(frozen=True)
class DialogueMessage:
    """One private message between two powers, scoped to a phase."""

    phase: str  # short phase code, e.g. "S1901M"
    sender: str
    recipient: str
    text: str


@dataclass(frozen=True)
class OrderResult:
    orders: list[str]
    chat: ChatResult
    prompt: str = ""  # the user message sent this call (for optional prompt logging)


@dataclass(frozen=True)
class MessagesResult:
    """Outgoing messages produced by Agent.negotiate(). Keyed by recipient power."""

    messages: dict[str, str]
    chat: ChatResult
    prompt: str = ""  # the user message sent this call (for optional prompt logging)


@dataclass(frozen=True)
class StrategyNote:
    """One self-authored strategy note: a power's 1-2 sentence plan at a moment."""

    phase: str  # short phase code, e.g. "S1901M"
    kind: str   # "initial" (before negotiation) or "revised" (after)
    text: str


@dataclass(frozen=True)
class StrategyResult:
    text: str        # the strategy/goals statement, stripped of whitespace
    chat: ChatResult
    prompt: str = ""


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
        other_powers = ", ".join(p for p in POWERS if p != self.power)
        return (
            f"{self.rules}\n\n"
            f"You are playing as {self.power} in a game of Diplomacy.\n\n"
            f"## Your persona\n{self.persona}\n\n"
            "## Output formats\n\n"
            "You will be asked for one of two things each call: **messages** "
            "(during negotiation) or **orders** (when it's time to commit moves).\n\n"
            "### When asked to send messages\n"
            "Reason briefly (one short paragraph) about who you want to talk to "
            "and what to say. Then end your response with a section beginning "
            "with `MESSAGES:` on its own line, followed by a JSON object mapping "
            "recipient power name to a short message (2–4 sentences). You may "
            "message any subset of the other powers — or none. Send 0 messages "
            "by emitting an empty object `{}`. Recipients must be one of: "
            f"{other_powers}.\n\n"
            "Negotiation runs as several rounds before each movement phase. "
            "Within a round, all powers send their messages simultaneously, so "
            "a recipient won't see what you send until the next round — and you "
            "may stay silent in any round. Use early rounds to probe and propose, "
            "later rounds to react, confirm, or adjust before orders are committed.\n\n"
            "Example:\n"
            "MESSAGES:\n"
            "{\n"
            f'  "{POWERS[0] if POWERS[0] != self.power else POWERS[1]}": "Let\'s '
            "stay out of each other's way this year. I'll leave the Balkans "
            "alone if you stay out of the west.\",\n"
            f'  "{POWERS[2] if POWERS[2] != self.power else POWERS[3]}": "Want to '
            'coordinate against a common rival?"\n'
            "}\n\n"
            "### When asked to submit orders\n"
            "Reason briefly about your strategy this phase, then emit orders "
            "using the legal-order strings EXACTLY as shown in the menu "
            "(anything not in the menu is rejected). In a movement or retreat "
            "phase, emit one order per unit. In a **build** phase, emit one "
            "order per build you are owed (your supply-center surplus), placing "
            "units in your open home centers — prefer building to waiving; only "
            "use `WAIVE` if you have a build but no legal home center for it, and "
            "never add a WAIVE once you've used all your builds. In a **disband** "
            "phase, emit exactly the required number of disbands.\n\n"
            "End your response with a section beginning with `ORDERS:` on its own "
            "line, followed by one order per line:\n\n"
            "ORDERS:\n"
            "A PAR - BUR\n"
            "A MAR - SPA\n"
            "F BRE - MAO\n\n"
            "Do not include any text after the trailing section."
        )

    # ------------------------------------------------------------------
    # Strategy / goals (self-authored, private to this agent)
    # ------------------------------------------------------------------

    def _strategy_call(
        self,
        state: GameState,
        *,
        kind: str,  # "initial" or "revised"
        dialogue: list[DialogueMessage] | None,
        strategy_history: list[StrategyNote] | None,
        max_tokens: int = 220,
        temperature: float = 0.6,
    ) -> StrategyResult:
        view = render_for_power(state, self.power)
        sh = format_strategy_history(strategy_history or [])
        body = f"{view}\n\n## Your strategy history (private to you)\n{sh}\n\n"
        if dialogue:
            db = format_dialogue_for_agent(dialogue, self.power)
            body += f"## Dialogue history (private to you)\n{db}\n\n"
        if kind == "initial":
            instruction = (
                f"It is the start of {state.phase}. Before negotiation begins, "
                "state your strategy and goals for this turn in 1-2 sentences. "
                "Be concrete (name powers and provinces you care about), reflect "
                "your standing relationships from the history above, and don't "
                "hedge. No preamble, no headings, just the strategy."
            )
        else:
            instruction = (
                f"Negotiation for {state.phase} is complete. Re-state your "
                "strategy and goals for the orders you're about to submit, in "
                "1-2 sentences. Acknowledge any updates from the negotiation "
                "(deals made, broken, or refused). No preamble, just the strategy."
            )
        user_msg = body + instruction
        chat = self.client.chat(
            system=self._system,
            messages=[Message(role="user", content=user_msg)],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return StrategyResult(text=chat.text.strip(), chat=chat, prompt=user_msg)

    def state_strategy(
        self,
        state: GameState,
        *,
        dialogue: list[DialogueMessage] | None = None,
        strategy_history: list[StrategyNote] | None = None,
    ) -> StrategyResult:
        return self._strategy_call(
            state, kind="initial", dialogue=dialogue, strategy_history=strategy_history,
        )

    def revise_strategy(
        self,
        state: GameState,
        *,
        dialogue: list[DialogueMessage] | None = None,
        strategy_history: list[StrategyNote] | None = None,
    ) -> StrategyResult:
        return self._strategy_call(
            state, kind="revised", dialogue=dialogue, strategy_history=strategy_history,
        )

    # ------------------------------------------------------------------
    # Negotiation
    # ------------------------------------------------------------------

    def negotiate(
        self,
        state: GameState,
        history: list[DialogueMessage] | None = None,
        *,
        round_index: int = 1,
        total_rounds: int = 1,
        strategy_history: list[StrategyNote] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> MessagesResult:
        view = render_for_power(state, self.power)
        dialogue_block = format_dialogue_for_agent(history or [], self.power)
        strategy_block = format_strategy_history(strategy_history or [])
        round_note = (
            f"This is negotiation round {round_index} of {total_rounds} before "
            f"orders for {state.phase}. All powers message simultaneously this "
            f"round, so others won't see yours until the next round. "
        )
        if round_index >= total_rounds:
            round_note += "This is the FINAL round — you commit orders next, so close any deals now. "
        elif round_index == 1:
            round_note += "Further rounds follow, so you can open threads now and react to replies later. "
        user_msg = (
            f"{view}\n\n"
            f"## Your strategy history (private to you)\n{strategy_block}\n\n"
            f"## Dialogue history (private to you)\n{dialogue_block}\n\n"
            f"{round_note}"
            f"Send private messages to any subset of the other powers (or none). "
            f"Keep each message to 2–4 sentences."
        )
        chat = self.client.chat(
            system=self._system,
            messages=[Message(role="user", content=user_msg)],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return MessagesResult(
            messages=parse_messages(chat.text, self.power), chat=chat, prompt=user_msg
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def submit_orders(
        self,
        state: GameState,
        *,
        dialogue: list[DialogueMessage] | None = None,
        strategy_history: list[StrategyNote] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> OrderResult:
        view = render_for_power(state, self.power)
        user_msg = view
        if strategy_history:
            sh = format_strategy_history(strategy_history)
            user_msg += f"\n\n## Your strategy history (private to you)\n{sh}"
        if dialogue:
            dialogue_block = format_dialogue_for_agent(dialogue, self.power)
            user_msg += f"\n\n## Dialogue history (private to you)\n{dialogue_block}"
        user_msg += f"\n\nIt is your turn. Submit your orders for {state.phase}."

        chat = self.client.chat(
            system=self._system,
            messages=[Message(role="user", content=user_msg)],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return OrderResult(orders=parse_orders(chat.text), chat=chat, prompt=user_msg)


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------


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
        s = s.lstrip("-*0123456789. ").strip()
        s = s.strip("`").strip()
        if s:
            out.append(s)
    return out


def parse_messages(text: str, sender: str) -> dict[str, str]:
    """Extract the JSON message object from an LLM response.

    Tolerates optional markdown code fences around the JSON. Returns an
    empty dict on any parse failure or if no MESSAGES: section is present.
    Drops any recipients that aren't valid powers, or that equal the sender.
    """
    if "MESSAGES:" not in text:
        return {}
    _, tail = text.rsplit("MESSAGES:", 1)
    tail = tail.strip()
    # Strip optional triple-backtick fences (with or without language tag)
    if tail.startswith("```"):
        first_nl = tail.find("\n")
        if first_nl == -1:
            return {}
        tail = tail[first_nl + 1 :]
        if "```" in tail:
            tail = tail[: tail.rfind("```")]
        tail = tail.strip()
    try:
        obj = json.loads(tail)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(obj, dict):
        return {}
    result: dict[str, str] = {}
    for k, v in obj.items():
        if isinstance(k, str) and isinstance(v, str) and k in POWERS and k != sender:
            result[k] = v
    return result


def validate_orders(state: GameState, power: str, orders: list[str]) -> tuple[list[str], list[str]]:
    """Return (valid, invalid) — partitioning the proposed orders against the legal-moves list."""
    legal_set: set[str] = set()
    for opts in state.legal_orders(power).values():
        legal_set.update(opts)
    valid, invalid = [], []
    for o in orders:
        (valid if o in legal_set else invalid).append(o)
    return valid, invalid


# ----------------------------------------------------------------------
# Dialogue formatting (rendered into the user message)
# ----------------------------------------------------------------------


def format_strategy_history(history: list[StrategyNote], *, recent: int = 6) -> str:
    """Render a power's own strategy/goals notes (most recent at the bottom).

    Capped to the last `recent` entries to bound token cost.
    """
    if not history:
        return "(No strategy notes yet — this is your first turn.)"
    notes = history[-recent:]
    out: list[str] = []
    for n in notes:
        tag = "initial" if n.kind == "initial" else "revised"
        out.append(f"- {n.phase} ({tag}): {n.text}")
    return "\n".join(out)


def format_dialogue_for_agent(history: list[DialogueMessage], power: str) -> str:
    """Render dialogue history as the agent sees it.

    Filters to messages this power sent or received; groups by phase;
    formats as `TO X: ...` / `FROM X: ...` lines.
    """
    visible = [m for m in history if m.sender == power or m.recipient == power]
    if not visible:
        return "(No prior dialogue.)"
    by_phase: dict[str, list[DialogueMessage]] = {}
    for m in visible:
        by_phase.setdefault(m.phase, []).append(m)
    lines: list[str] = []
    for phase in sorted(by_phase.keys()):
        lines.append(f"### {phase}")
        for m in by_phase[phase]:
            if m.sender == power:
                lines.append(f"  TO {m.recipient}: {m.text}")
            else:
                lines.append(f"  FROM {m.sender}: {m.text}")
        lines.append("")
    return "\n".join(lines).rstrip()
