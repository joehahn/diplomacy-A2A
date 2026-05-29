# results/

Rendered transcripts of game runs land here. The canonical run is **committed**
to the repo so visitors can read the interesting output without spending money
on API calls; throwaway runs live in `scratch/` (gitignored) instead.

Each run lands as a directory:

- `transcript.jsonl` — structured event log (one event per line, the source of truth)
- `report.md`        — human-readable markdown postmortem rendered from the JSONL
- `initial.svg` — the opening board; `<short-phase>.svg` — that phase's orders as
  arrows on the start-of-phase board; `<short-phase>.result.svg` — the board after
  the phase resolved (e.g. `S1901M.svg` / `S1901M.result.svg`)
- `index.html` + `start.html` + one `<short-phase>.html` per phase — slideshow
  viewer. Each slide reads top-to-bottom: orders, then the orders map and the
  resulting board, then the negotiation that leads into the *next* movement phase
  (so you read the talk, then click ahead to see what it produced). The opening
  `start.html` shows the initial board and the first round of negotiation.
  **Easiest entry point**: open `index.html` and click through.
- `prompts.jsonl` / `prompts.md` — only present when the run was launched with
  `--log-prompts`; contains every agent's exact prompt and response for the
  first `--log-prompts-years` years (default 1).

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Canonical run

The canonical configuration is:

```bash
python -m diplomacy_a2a --log-prompts
```

Everything else takes its default value — Sonnet 4.6, 5 game-years, 3
negotiation rounds per movement phase, agent memory = 3 movement turns,
self-authored strategy notes on. `--log-prompts` saves the exact prompt +
response pair for every agent call during the **first** game-year (the
`--log-prompts-years` default), so the opening play is auditable down to the
token without the later phases bloating the dump.

Expected cost / wall-time at current Sonnet rates: ≈$8 / ≈80 minutes for the
full 5-year game. The rendered slideshow + `prompts.md` are committed when a
new canonical lands.

*(The previous Sonnet 2-year canonical at `20260528T214253Z/` was deleted on
2026-05-29 in favor of the new 5-year configuration. A replacement render is
pending.)*
