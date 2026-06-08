# CLAUDE.md

Claude-specific working notes. **`README.md` is the user-facing doc** (architecture,
setup, intended commands) — read it for orientation; this file only captures things
that aren't there or that an agent would otherwise get wrong.

## What "good" means here

The deliverable is the **negotiation transcript**, not winning. When evaluating a
change, judge it by whether it produces clearer/richer agent dialogue and a faithful
record of it — not by game outcomes. This is a portfolio demo, so output legibility
(reports, HTML viewer) matters as much as correctness.

## Standing rules

- **Never roll your own Diplomacy rules or adjudication.** All rules/legality/
  adjudication go through Meta's `diplomacy` library (MIT, DATC-compliant), wrapped
  thinly in `diplomacy_a2a/game/`. If you're tempted to write order-resolution logic,
  stop — find the library call instead.
- **Model IDs live only in `config.py`** (`DEFAULT_MODEL`, `SMOKE_MODEL`,
  `GATEWAY_MODELS`), pinned not "latest" so reruns stay comparable. Don't hardcode
  model strings anywhere else; override per-call if needed.
- **`LLMClient` (`llm/client.py`) is the provider seam.** Two impls satisfy it:
  `AnthropicClient` (default, direct) and `GatewayClient` (OpenRouter, for cheaper
  models). `make_client` in `llm/factory.py` routes by model id (`claude-*` to
  Anthropic, else the gateway). A further provider is a new impl behind the protocol,
  not a refactor.

## Current reality vs. the README (as of this writing)

The CLI in `cli.py` / `__main__.py` has three subcommands:

  - `run [opts]` — execute a game (LLM, real cost). All previous top-level
    flags (`--model`, `--years`, `--rounds`, `--log-prompts`,
    `--log-prompts-years`, `--power-model`, `--power-memory`, `--memory`,
    `--smoke`, `--results-dir`, `--quiet`) live here, plus two new flags:
    `--no-render` (skip the auto-render at end of game) and
    `--with-commentary` (also run the LLM commentary post-pass and re-render).
  - `render <run-dir> [--with-commentary] [--refresh-commentary]` —
    re-derive maps / report.md / HTML slideshow from a finished transcript.
    No LLM. Sub-second. Use this when iterating on viewer code.
  - `commentary <run-dir> [--model M]` — generate `commentary.json` only
    (no render). Useful when scripting or testing a different commentator
    model.

Back-compat: `python -m diplomacy_a2a [opts]` with no subcommand is parsed
as `run [opts]` so older invocations keep working.

The function `run_game(...)` in `runner.py` is still the programmatic entry
for the game step; it now takes a `render: bool = True` parameter so that
end-of-game rendering can be skipped when callers (the `--with-commentary`
flow) want to render once after commentary lands. `tests/test_smoke.py` is
still a single `@pytest.mark.skip` stub; smoke is effectively covered by
`python -m diplomacy_a2a run --smoke` (Haiku, 1yr, 1 round, pennies).

## Running & cost

- Activate the venv first: `source .venv/bin/activate`. Needs an Anthropic key in
  `.env` (copy `.env.example`).
- For cheap iteration, drive `run_game` with `model=SMOKE_MODEL` (Haiku) and small
  `years` / `max_phases`. Caveat: Haiku's 2048-token cacheable-prefix minimum means
  short smoke prompts may not exercise the cache path (see comment in `config.py`).
- Full grid runs (persona × matchup × seed) cost ~hundreds of dollars. Default to
  small/cheap unless explicitly asked for a full run.
- Tests: `pytest` (currently only the skipped smoke stub).

## Artifacts & git

- Curated `results/<run-id>/` transcripts **are committed** on purpose, so visitors
  see output without spending money. `transcript.jsonl` lives at the top level
  as the source of truth; `dashboard/report.md` / `dashboard/*.svg` /
  `dashboard/index.html` are derived from it (rendered under a `dashboard/`
  subfolder so the derived artifacts are visually separated from the LLM
  outputs).
- `scratch/` and `*.log` are gitignored — put throwaway experiments there.
