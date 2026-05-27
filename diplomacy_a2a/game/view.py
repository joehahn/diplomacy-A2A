"""Render game state into the per-power view shown to an LLM agent.

Diplomacy is open information — every power sees every unit's position
— so the view is the same factual content for everyone. What varies
per power is the framing ("YOUR units", "YOUR supply centers") and the
legal-moves list, which is filtered to the addressee's units this turn.

The text returned here is the variable tail of the prompt — combined
with the cached system prefix (rules + persona) for each LLM call.
"""
from __future__ import annotations

from diplomacy_a2a.game.state import POWERS, GameState
from diplomacy_a2a.narration import narrate_phase


def render_for_power(state: GameState, power: str) -> str:
    if power not in POWERS:
        raise ValueError(f"Unknown power: {power!r}. Expected one of {POWERS}.")

    lines: list[str] = []
    lines.append(f"## Current phase: {state.phase}  ({state.short_phase})")
    lines.append("")

    # What happened last turn — plain-English recap of every power's orders
    # and how they resolved (bounces, dislodgements, supports), so you can
    # see who helped or attacked whom without decoding raw order syntax.
    recap = state.recent_resolved()
    if recap:
        lines.append("## What happened last turn")
        for short, orders, results in recap:
            lines.append(f"### {short}")
            for p, text in narrate_phase(orders, results, powers_order=list(POWERS)):
                marker = " ← YOU" if p == power else ""
                lines.append(f"- {p}{marker}: {text}")
        lines.append("")

    lines.append("## Unit positions (all powers — Diplomacy is open information)")
    for p in POWERS:
        units = state.units(p)
        marker = " ← YOU" if p == power else ""
        lines.append(f"- {p}{marker}: {', '.join(units) if units else '(none)'}")
    lines.append("")
    lines.append("## Supply centers")
    for p in POWERS:
        centers = state.centers(p)
        marker = " ← YOU" if p == power else ""
        lines.append(f"- {p}{marker} ({len(centers)}): {', '.join(centers) if centers else '(none)'}")
    lines.append("")

    legal = state.legal_orders(power)
    if legal:
        lines.append(f"## Your legal orders this phase ({state.short_phase})")
        lines.append(
            "Emit one order per unit, using EXACTLY one of the strings below for each location. "
            "Anything not in this list will be rejected by the adjudicator."
        )
        for loc in sorted(legal):
            options = legal[loc]
            lines.append(f"")
            lines.append(f"### {loc} ({len(options)} options)")
            for o in options:
                lines.append(f"  - `{o}`")
    else:
        lines.append(f"## You have no units to order this phase ({state.short_phase}).")

    return "\n".join(lines)
