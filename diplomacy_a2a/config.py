"""Centralized constants: model IDs, defaults, cost estimates.

Model IDs are pinned (not "latest") so reruns are comparable across
model releases. Override per-call if you need to; do not hardcode
model strings elsewhere in the codebase.
"""
from __future__ import annotations

DEFAULT_MODEL = "claude-opus-4-7"
# Haiku has a 2048-token minimum for the cacheable system prefix
# (Opus/Sonnet: 1024). If smoke-mode prompts run shorter than that,
# caching silently no-ops — fine for cost (Haiku is cheap), but means
# smoke mode does NOT exercise the cache code path.
SMOKE_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 1.0
