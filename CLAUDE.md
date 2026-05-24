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
- **Model IDs live only in `config.py`** (`DEFAULT_MODEL`, `SMOKE_MODEL`), pinned not
  "latest" so reruns stay comparable. Don't hardcode model strings anywhere else;
  override per-call if needed.
- **`LLMClient` (`llm/client.py`) is the provider seam.** A second provider should be
  a new implementation behind that protocol, not a refactor. `AnthropicClient` is the
  only v1 impl.

## Current reality vs. the README (as of this writing)

The README documents the *intended* CLI. It isn't wired up yet:

- `python -m diplomacy_a2a ...` → `cli.main()` raises `NotImplementedError`. The
  documented `smoke` / `run` / `experiment` subcommands do **not** work yet.
- `tests/test_smoke.py` is a single `@pytest.mark.skip` stub.
- The **real, working entry point is `run_game(...)` in `runner.py`** — a keyword-only
  function called programmatically. The committed `results/<run-id>/` artifacts were
  produced this way, not via the CLI.

When wiring up the CLI/tests, make them call `run_game`, and update the README so its
commands stop being aspirational.

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
  see output without spending money. `transcript.jsonl` is the source of truth;
  `report.md` / `*.svg` / `index.html` are rendered from it.
- `scratch/` and `*.log` are gitignored — put throwaway experiments there.
