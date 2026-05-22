# results/

Pre-rendered transcripts of game runs. These are **committed** to the
repo so visitors can read the interesting output without spending
money on API calls.

Each run lands as:

- `<run-id>.jsonl` — structured event log (one event per line)
- `<run-id>.md` — human-readable markdown postmortem rendered from the JSONL

Naming convention: `<date>-<personas>-<seed>.jsonl`, e.g.
`2026-05-23-aggressor-vs-pacifist-seed42.jsonl`.
