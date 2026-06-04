"""Post-game agent interrogation (the `ask` subcommand).

Reconstructs a finished game from one power's point of view, straight from
its committed `transcript.jsonl`, and puts a free-form question to that power.
The agents are stateless, so there is no cache to reload: the transcript is
the complete record of what each agent saw and said, including its actual
per-turn strategy notes, orders, and private dialogue. We rebuild that record,
give it back to a fresh instance of the same persona, and ask.

The answer is therefore grounded in the agent's own recorded words rather than
a free invention, though it is a reconstruction (a fresh call), not the literal
instance that played, so it cannot recover hidden reasoning that was never
written down.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from diplomacy_a2a.agent import _load_default_rules, parse_messages, rules_with_tables
from diplomacy_a2a.config import DEFAULT_MODEL
from diplomacy_a2a.game.state import POWERS
from diplomacy_a2a.llm.client import ChatResult, LLMClient, Message

_SEASON = {"S": 0, "F": 1, "W": 2}
_PTYPE = {"M": 0, "R": 1, "A": 2}


def _phase_key(phase: str) -> tuple[int, int, int]:
    """Chronological sort key for a short phase code like `S1901M` / `W1903A`."""
    return (int(phase[1:5]), _SEASON[phase[0]], _PTYPE[phase[5]])


def _strip_trailing_block(text: str) -> str:
    """Drop any `MESSAGES:` / `ORDERS:` block an agent erroneously appended to a
    strategy note, so the note shows only its prose (dialogue is rendered
    separately from its own records)."""
    cut = len(text)
    for marker in ("MESSAGES:", "ORDERS:"):
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    return text[:cut].strip()


def _load(jsonl_path: Path) -> tuple[dict, list[dict]]:
    records = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    started = next((r for r in records if r.get("type") == "run_started"), None)
    if started is None:
        raise SystemExit(f"{jsonl_path} has no run_started record (not a finished run?)")
    return started, records


def build_power_log(records: list[dict], power: str, *, upto: str | None = None,
                    with_dialogue: bool = True) -> str:
    """Render the game from `power`'s perspective as markdown: its strategy
    notes, orders, the adjudicated results for its units, the standings
    trajectory, and (optionally) its private dialogue, phase by phase.
    """
    cutoff = _phase_key(upto) if upto else None
    strat: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    orders: dict[str, tuple[list[str], list[str]]] = {}
    results: dict[str, dict[str, list[str]]] = {}
    centers: dict[str, dict[str, list[str]]] = {}
    sent: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    recv: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)

    for r in records:
        t = r.get("type")
        ph = r.get("phase") or r.get("resolved_phase")
        if not ph or ph[0] not in _SEASON:
            continue
        if cutoff and _phase_key(ph) > cutoff:
            continue
        if t == "agent_strategy" and r.get("power") == power:
            strat[ph].append((r.get("kind", ""), r.get("text", "")))
        elif t == "orders_submitted" and r.get("power") == power:
            orders[ph] = (r.get("valid", []), r.get("invalid", []))
        elif t == "phase_resolved":
            results[r["resolved_phase"]] = r.get("results", {})
            centers[r["resolved_phase"]] = r.get("centers", {})
        elif t == "agent_messages" and with_dialogue:
            sender = r.get("power", "")
            if sender == power:
                for rec, msg in parse_messages(r.get("text", ""), power).items():
                    sent[ph].append((rec, msg))
            else:
                for rec, msg in parse_messages(r.get("text", ""), sender).items():
                    if rec == power:
                        recv[ph].append((sender, msg))

    # Movement phases in order define the spine of the log.
    phases = sorted({p for p in list(orders) + list(strat)}, key=_phase_key)
    last_resolved = max(centers, key=_phase_key) if centers else None

    lines = [f"You played {power} in this game of Diplomacy."]
    if last_resolved and centers.get(last_resolved):
        c = centers[last_resolved]
        standings = ", ".join(
            f"{p} {len(c.get(p, []))}" for p in sorted(c, key=lambda p: -len(c.get(p, [])))
        )
        lines.append(f"\nStandings at {last_resolved}: {standings}.")
    lines.append("\n## Your record, phase by phase (your strategy, orders, results, and dialogue)\n")

    for ph in phases:
        lines.append(f"### {ph}")
        for kind, text in strat.get(ph, []):
            lines.append(f"- Your strategy ({kind}): {_strip_trailing_block(text)}")
        valid, invalid = orders.get(ph, ([], []))
        if valid:
            lines.append(f"- Your orders: {'; '.join(valid)}")
        if invalid:
            lines.append(f"- Your orders rejected as illegal: {'; '.join(invalid)}")
        # Adjudication outcomes for this power's own units (non-empty tokens only).
        unit_locs = {o.split()[1].split("/")[0] for o in valid if len(o.split()) >= 2}
        res = results.get(ph, {})
        notable = [f"{u} ({', '.join(toks)})" for u, toks in res.items()
                   if toks and u.split()[1].split("/")[0] in unit_locs]
        if notable:
            lines.append(f"- Results for your units: {'; '.join(notable)}")
        if ph in centers:
            c = centers[ph]
            lines.append(f"- Your supply-center count after this phase: {len(c.get(power, []))}")
        for rec, msg in sent.get(ph, []):
            lines.append(f"- You said to {rec}: {msg}")
        for sender, msg in recv.get(ph, []):
            lines.append(f"- {sender} said to you: {msg}")
        lines.append("")
    return "\n".join(lines)


def interview(run_dir: Path, power: str, question: str, *, phase: str | None = None,
              model: str | None = None, with_dialogue: bool = True,
              client: LLMClient | None = None) -> tuple[str, ChatResult, str]:
    """Ask `power` a question about its play in the finished run at `run_dir`.

    Returns (answer_text, chat_result, model_used).
    """
    power = power.upper()
    if power not in POWERS:
        raise SystemExit(f"Unknown power {power!r}; expected one of {', '.join(POWERS)}")
    jsonl = Path(run_dir) / "transcript.jsonl"
    if not jsonl.exists():
        raise SystemExit(f"No transcript.jsonl in {run_dir}")

    started, records = _load(jsonl)
    personas = started.get("personas", {})
    if power not in personas:
        raise SystemExit(f"{power} not found in this run's personas")
    persona = personas[power]
    if model is None:
        model = started.get("power_models", {}).get(power) or started.get("model") or DEFAULT_MODEL
    adjacency_table = bool(started.get("adjacency_table", True))

    if client is None:
        from diplomacy_a2a.llm.anthropic_client import AnthropicClient
        client = AnthropicClient(model=model)

    rules = rules_with_tables(_load_default_rules(), power, adjacency_table)
    system = (
        f"{rules}\n\n"
        f"You played as {power} in a completed game of Diplomacy.\n\n"
        f"## Your persona\n{persona}\n\n"
        "## Interview\n"
        "The game is over. You are now being interviewed about your own play. A "
        "record of the game from your point of view follows: your strategy notes, "
        "the orders you submitted, how they resolved, and your private dialogue. "
        "Answer the question in plain prose, no `ORDERS:` or `MESSAGES:` block and "
        "no order syntax. Be honest and specific: ground your answer in your actual "
        "orders, notes, and the board above. If you cannot reconstruct a genuine "
        "reason for a decision, say so plainly rather than inventing a justification."
    )
    log = build_power_log(records, power, upto=phase, with_dialogue=with_dialogue)
    scope = f" as of {phase}" if phase else ""
    user = (
        f"{log}\n\n"
        f"## Question (about your play{scope})\n{question}"
    )
    chat = client.chat(
        system=system,
        messages=[Message(role="user", content=user)],
        max_tokens=800,
        temperature=0.3,
    )
    return chat.text.strip(), chat, model
