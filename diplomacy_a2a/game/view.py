"""Render game state into the per-power view shown to an LLM agent.

Each agent sees only what its power would see — its units, the board,
the supply-center ownership, the dialogue it was a party to. Returns
plain text (or structured JSON-as-text) suitable for inclusion in a
prompt.
"""
from __future__ import annotations


def render_for_power(state: "GameState", power: str) -> str:  # type: ignore[name-defined]
    raise NotImplementedError
