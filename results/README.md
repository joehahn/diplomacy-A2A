# results/

Pre-rendered transcripts of game runs. These are **committed** to the
repo so visitors can read the interesting output without spending
money on API calls.

Each run lands as a directory:

- `transcript.jsonl` — structured event log (one event per line, the source of truth)
- `report.md`        — human-readable markdown postmortem rendered from the JSONL
- `<short-phase>.svg` — one map image per phase (e.g. `S1901M.svg`), embedded inline in the markdown

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Canonical runs

### `20260524T031616Z/` — first baseline, no negotiation

The first end-to-end run of the artifact pipeline. Seven Sonnet-backed
agents with default personality stubs played 2 years (7 phases) of
Diplomacy with **no negotiation between turns** — each agent picked
orders from its legal-moves menu independently. Cost: ~$0.35.

Notable dynamics:

- Russia pressed east and finished on top (6 centers) — the
  "expansionist" persona delivered.
- Italy moved toward the Balkans (`A TYR - TRI`, `A APU - GRE via convoy`)
  — the "scheming" persona in action.
- One invalid order across the entire run (Austria S1902M), caught by
  our validator and filtered before reaching the adjudicator.

Open `results/20260524T031616Z/report.md` to read the postmortem.
SVGs render inline in any markdown viewer that supports HTML
`<img>` tags (GitHub does).
