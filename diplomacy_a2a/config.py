"""Centralized constants: model IDs, defaults, cost estimates.

Model IDs are pinned (not "latest") so reruns are comparable across
model releases. Override per-call if you need to; do not hardcode
model strings elsewhere in the codebase.
"""
from __future__ import annotations

DEFAULT_MODEL = "claude-opus-4-7"
SMOKE_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 1.0
