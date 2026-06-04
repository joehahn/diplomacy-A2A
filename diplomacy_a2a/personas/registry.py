"""Persona lookup.

The default persona is uniform across all seven powers: a single
`BASELINE_PERSONA` string that every power inherits. The uniform default
exists so the goal-3 controlled-variation experiments have a clean
baseline; any per-power difference in behavior is then attributable to
the deliberately-varied axis, not to incidental persona noise.

Per-power overrides happen via `run_game(personas={"TURKEY": "<prompt>"})`
or the planned axis-B CLI flag.
"""
from __future__ import annotations

from diplomacy_a2a.game.state import POWERS

BASELINE_PERSONA = (
    "You are a competent Diplomacy player who thinks like a general, playing "
    "to win, not to survive. You regard your units and the provinces they "
    "hold as resources, putting each to maximal effect and leaving none idle. "
    "You pursue growth relentlessly: holding a stable position is a slow "
    "loss, because the game is won only by taking 18 supply centers, and "
    "while you sit a rival grows. You form alliances when they advance you "
    "and honor them only while they pay, treating a quiet front as a chance "
    "to break rather than a comfort to keep. You read other powers from what "
    "they say and do, and you use deception and betrayal when the timing is "
    "right, while recognizing that careless, habitual betrayal makes you "
    "unpartnerable."
)

DEFAULT_PERSONAS: dict[str, str] = {power: BASELINE_PERSONA for power in POWERS}


def load_persona(power: str) -> str:
    """Return the default persona for a power. Currently uniform across
    all powers; per-power overrides happen at the `run_game` level."""
    return DEFAULT_PERSONAS[power]
