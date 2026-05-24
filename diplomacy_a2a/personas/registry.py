"""Persona lookup.

For v1 we ship a placeholder set of 7 power-indexed personas — distinct
enough to demonstrate that personas influence strategy, but written
casually. The proper persona library (power-agnostic, with deliberately
contrasting strategic styles) comes when we build the experimental
grid.
"""
from __future__ import annotations

DEFAULT_PERSONAS: dict[str, str] = {
    "FRANCE":  "A pragmatic, conservative player who prefers stable alliances and avoids unnecessary risks.",
    "GERMANY": "An opportunist — seize tactical chances, willing to pivot alliances when payoffs flip.",
    "ENGLAND": "Cautious and naval-focused; build a strong fleet position before committing to aggression.",
    "ITALY":   "Ambiguous and scheming; keep options open, prefer surprise moves over telegraphed campaigns.",
    "AUSTRIA": "Defensive and central; hold the position, broker peace between feuding neighbors.",
    "RUSSIA":  "Expansionist on both fronts; press for territory wherever weakness appears.",
    "TURKEY":  "Patient and long-game; build slowly, exploit late-game momentum.",
}


def load_persona(power: str) -> str:
    """Return the default persona for a power. Will be extended for grid experiments."""
    return DEFAULT_PERSONAS[power]
