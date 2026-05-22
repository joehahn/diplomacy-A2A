"""Structured transcript writer + simple markdown renderer.

Game runs write to JSONL (one event per line: messages, orders,
adjudication results) under `results/`. A small renderer turns that
JSONL into a human-readable markdown postmortem — the interview-ready
artifact.
"""
from __future__ import annotations


def write_event() -> None:
    raise NotImplementedError


def render_markdown() -> None:
    raise NotImplementedError
