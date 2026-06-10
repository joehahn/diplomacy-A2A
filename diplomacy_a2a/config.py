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

# LLM-capability axis (Axis A) roster: a top-shelf and a low-cost model each
# rotate through all seven powers against a DEFAULT_MODEL (Sonnet) field. Pinned
# so the sweep is reproducible. Driven by experiments/llm_axis.py.
LLM_AXIS_TOPSHELF = "claude-opus-4-8"   # frontier reference (direct Anthropic)
LLM_AXIS_LOWCOST = "xiaomi/mimo-v2.5"   # best-value cheap model (gateway)

DEFAULT_MAX_TOKENS = 1024
# Order generation gets a larger cap than other calls. Verbose models (notably
# the gateway's Kimi K2.6) narrate their order reasoning at length and can spend
# the whole budget before emitting the order block, leaving the power with no
# parseable orders. max_tokens is a ceiling, not a target, so a model that
# finishes early (e.g. Sonnet) pays nothing for the extra headroom.
ORDER_MAX_TOKENS = 4096
# Strategy and negotiation calls ask for only a few sentences, but gateway
# models that bill hidden reasoning against max_tokens (DeepSeek V4-Flash,
# Kimi K2.6) can spend a tight budget entirely on reasoning and return empty
# content (finish_reason=length). The old 500/1024 caps left no room; these
# give reasoning headroom. As with ORDER_MAX_TOKENS, the cap is a ceiling, so
# models that finish early pay nothing for it.
STRATEGY_MAX_TOKENS = 2048
NEGOTIATION_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 1.0
