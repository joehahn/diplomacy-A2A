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

## Canonical run

### `20260526T231112Z/` — **3-round negotiation**

Seven Sonnet-backed agents, 2 years, with **three rounds** of private pairwise
messaging before each movement phase — and the agents are told the protocol, so
they probe in round 1, negotiate in round 2, and close deals in round 3. 7 phases,
~$2.20, ~23 minutes.

The rounds produce explicit, multi-step deal-making and openly telegraphed
betrayals. Highlight, F1901M:

- **Italy → Austria** (round 3): *"I'm making a move toward Trieste this fall —
  not as a hostile act, but I want to be honest rather than surprise you."*
  Italy then ordered **`A VEN - TRI`** (into Austria's home center). Austria,
  having heard the warning that same round, ordered **`A TYR - TRI`** to defend —
  a clean case of dialogue driving orders, and an *honest* stab.
- **Turkey → Austria**: ceded Greece (*"it's yours this fall"*) and slid
  **`A BUL - SER`** into the center Austria vacated moving to Greece — a
  coordinated handoff negotiated across the three rounds.

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260526T231112Z/index.html)
(GitHub Pages) to flip through the maps and dialogue phase by phase.
