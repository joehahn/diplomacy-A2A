"""One turn's negotiation phase — N rounds of pairwise private messages.

Powers exchange private messages with each other before committing
orders. The number of rounds is a tunable knob (more rounds = richer
dialogue + higher cost).
"""
from __future__ import annotations


def run_negotiation_phase() -> None:
    raise NotImplementedError
