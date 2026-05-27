"""Optional LLM-written strategic commentary for a finished game.

Decoupled from the game loop on purpose: call `generate_commentary` on a
finished `transcript.jsonl` when you want narrator-style "who's threatening /
cooperating / backstabbing" notes for the slideshow. It is **not** run during
games, so a full experiment grid stays cheap — the viewer merely *reads* the
`commentary.json` this produces (and omits the block if it's absent).

Unlike the deterministic `narration` (ground truth), this is interpretation:
useful color for a human reader, never fed back to the agents.
"""
from __future__ import annotations

import json
from pathlib import Path

from diplomacy_a2a.llm.client import LLMClient, Message
from diplomacy_a2a.narration import narrate_phase

_SYSTEM = (
    "You are a sharp, concise Diplomacy commentator. Given what each power did in "
    "a phase and the private messages they exchanged just before it, write 2-4 "
    "sentences of strategic commentary for a spectator: who is now threatening whom "
    "(name powers and provinces), who appears to be cooperating, and any apparent "
    "betrayal — a power that promised one thing in the messages but did another. Be "
    "concrete and brief. This is your read of the board, not a recap; don't restate "
    "every move and don't hedge with disclaimers."
)


def _phase_context(long_name: str, narration, standings, dialogue) -> str:
    lines = [f"Phase: {long_name}", "", "Supply-center standing:"]
    lines.append("  " + ", ".join(f"{p} {n}" for p, n in standings))
    lines.append("")
    lines.append("What each power did this phase:")
    for power, text in narration:
        lines.append(f"  {power}: {text}")
    lines.append("")
    if dialogue:
        lines.append("Private messages exchanged just before this phase:")
        for sender, recipient, text in dialogue:
            lines.append(f"  {sender} -> {recipient}: {text}")
    else:
        lines.append("(No private messages preceded this phase.)")
    return "\n".join(lines)


def generate_commentary(
    jsonl_path: Path,
    client: LLMClient,
    *,
    out_path: Path | None = None,
    max_tokens: int = 260,
    temperature: float = 0.7,
) -> dict[str, str]:
    """Write per-phase strategic commentary to commentary.json; return it.

    One LLM call per phase, grounded in that phase's deterministic narration,
    supply-center standing, and the negotiation that preceded it (so it can
    spot promise-vs-action betrayals).
    """
    events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]

    phase_order: list[tuple[str, str]] = []  # (short, long)
    orders_by_phase: dict[str, dict[str, list[str]]] = {}
    results_by_phase: dict[str, dict[str, list[str]]] = {}
    dialogue_by_phase: dict[str, list[tuple[str, str, str]]] = {}
    centers_by_phase: dict[str, dict[str, list[str]]] = {}
    for e in events:
        if e["type"] == "phase_started":
            phase_order.append((e.get("short_phase", "?"), e.get("phase", "?")))
        elif e["type"] == "orders_submitted":
            orders_by_phase.setdefault(e["phase"], {})[e["power"]] = e.get("valid", [])
        elif e["type"] == "agent_messages":
            for recipient, text in e.get("messages", {}).items():
                dialogue_by_phase.setdefault(e["phase"], []).append((e["power"], recipient, text))
        elif e["type"] == "phase_resolved" and e.get("resolved_phase"):
            results_by_phase[e["resolved_phase"]] = e.get("results", {})
            centers_by_phase[e["resolved_phase"]] = e.get("centers", {})

    commentary: dict[str, str] = {}
    for short, long_name in phase_order:
        orders = orders_by_phase.get(short, {})
        if not orders:
            continue
        narration = narrate_phase(orders, results_by_phase.get(short, {}))
        centers = centers_by_phase.get(short, {})
        standings = sorted(((p, len(c)) for p, c in centers.items()), key=lambda kv: -kv[1])
        context = _phase_context(long_name, narration, standings, dialogue_by_phase.get(short, []))
        chat = client.chat(
            system=_SYSTEM,
            messages=[Message(role="user", content=context)],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        commentary[short] = chat.text.strip()

    out_path = out_path or (jsonl_path.parent / "commentary.json")
    out_path.write_text(json.dumps(commentary, indent=2))
    return commentary
