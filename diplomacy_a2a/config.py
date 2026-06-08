"""Centralized constants: model IDs, defaults, cost estimates.

Model IDs are pinned (not "latest") so reruns are comparable across
model releases. Override per-call if you need to; do not hardcode
model strings elsewhere in the codebase.
"""
from __future__ import annotations

DEFAULT_MODEL = "claude-sonnet-4-6"
# Haiku has a 2048-token minimum for the cacheable system prefix
# (Opus/Sonnet: 1024). If smoke-mode prompts run shorter than that,
# caching silently no-ops — fine for cost (Haiku is cheap), but means
# smoke mode does NOT exercise the cache code path.
SMOKE_MODEL = "claude-haiku-4-5-20251001"

# Cheap-model candidates reached through OpenRouter (see llm/gateway_client.py).
# Any non-"claude-" id routes to the gateway. Pinned, not "latest", so reruns
# stay comparable. Confirm each slug against https://openrouter.ai/models before
# a paid run; the exact "provider/model" strings change as versions ship.
GATEWAY_MODELS = {
    "deepseek": "deepseek/deepseek-v4-flash",
    "kimi": "moonshotai/kimi-k2.6",
    "minimax": "minimax/minimax-m3",
    "gemini": "google/gemini-3.5-flash",  # fallback
}

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 1.0
