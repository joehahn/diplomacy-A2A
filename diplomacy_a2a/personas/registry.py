"""Persona lookup.

The default persona is uniform across all seven powers: a single
`BASELINE_PERSONA` string that every power inherits unless explicitly
overridden. The uniform default exists so the goal-3 controlled-variation
experiments have a clean baseline; any per-power difference in behavior
is then attributable to the deliberately-varied axis, not to incidental
persona noise.

Per-power overrides land via `run_game(personas={"TURKEY": "<prompt>"})`
or the planned axis-B CLI flag. An earlier version of this file shipped
7 distinct power-keyed placeholders; those were a research-design wart
(they confounded every controlled comparison) and are gone as of this
commit.

The committed canonical run under `results/20260529T225943Z/` was
produced before this change and therefore reflects the older per-power
personas. It will be refreshed in a later run; the transcript is left
in place for continuity until then.
"""
from __future__ import annotations

from diplomacy_a2a.game.state import POWERS

BASELINE_PERSONA = (
    "You are a competent Diplomacy player pursuing your own interest. "
    "You form alliances when they advance your goals and honor them while "
    "they serve you. You defend solid positions and take calculated risks "
    "when the payoff justifies it. You read other powers' intentions from "
    "what they say and do, and you recognize that lies are sometimes worth "
    "their cost while habitual betrayal makes you unpartnerable."
)

DEFAULT_PERSONAS: dict[str, str] = {power: BASELINE_PERSONA for power in POWERS}


def load_persona(power: str) -> str:
    """Return the default persona for a power. Currently uniform across
    all powers; per-power overrides happen at the `run_game` level."""
    return DEFAULT_PERSONAS[power]
