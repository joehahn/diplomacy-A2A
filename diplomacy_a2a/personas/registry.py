"""Persona lookup — load markdown system prompts from prompts/.

A persona is a named bundle of (system-prompt text, optional config knobs
like temperature). Personas are the experimental variable for the
6-persona × 4-matchup × 5-seed grid.
"""
from __future__ import annotations


def load_persona(name: str) -> str:
    raise NotImplementedError
