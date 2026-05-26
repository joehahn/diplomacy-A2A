# results/

Pre-rendered transcripts of game runs. These are **committed** to the
repo so visitors can read the interesting output without spending
money on API calls.

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

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Canonical runs

### `20260524T034819Z/` — **with 1-round negotiation** (current canonical demo)

Seven Sonnet-backed agents playing 2 years of Diplomacy with **one round
of private pairwise messaging** before each movement phase. 7 phases,
~$0.88, ~12 minutes.

The dialogue is the headline feature here. Selected highlights:

- **Italy → Austria** in S1901M: "I'd like to propose a friendly opening
  between us — I have no designs on Trieste."
  **Italy's actual orders** in F1901M then moved on Trieste. Classic
  CICERO-flavored stab captured in transcript.
- By F1902M, multiple powers had independently identified Turkey as the
  rising threat and were proposing coalitions against it
  ("Turkey at 5 centers is a real threat to both of us — I'm pushing
  to check them this fall").

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260524T034819Z/index.html)
(GitHub Pages) to flip through the maps and dialogue phase by phase.

### `20260524T031616Z/` — no-negotiation baseline (for comparison)

Same setup, same personas, but agents act independently each turn
with no inter-agent dialogue. Useful as the "what does dialogue
actually buy us?" comparison run. 7 phases, ~$0.35.

[**View this run's slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260524T031616Z/index.html)
(GitHub Pages).
