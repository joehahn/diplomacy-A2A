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

### `20260527T133022Z/` — **3-round negotiation, with turn narration**

Seven Sonnet-backed agents, 2 years, with **three rounds** of private pairwise
messaging before each movement phase — agents are told the protocol, so they
probe in round 1, negotiate in round 2, and close in round 3. Each slide shows a
plain-English **"what happened this phase"** narration beside the maps, and that
same recap is fed back to the agents so they reason about prior-turn outcomes.
6 phases, ~$2.22, ~23 minutes.

Highlights:

- **The narration loop closing** — after Germany and Russia *both bounced* trying
  to take Sweden in F1901M, Germany opens F1902M with *"The SWE situation last
  spring was frustrating for both of us — I'd like to finally resolve it this
  fall. If F BOT supports F DEN into SWE, I take it cleanly and you get a favor
  owed."* The agent remembered the bounce (from the recap) and proposed a fix.
- **Honest pressure** — Italy, stuck at 4 centers, to Austria: *"I need to be
  honest — you're at 5 centers and I'm stuck at 4… I need a deal, not just
  promises. Can you support my move into SMY?"* — a coalition forming around
  who's pulling ahead.

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260527T133022Z/index.html)
(GitHub Pages) to flip through the maps, narration, and dialogue phase by phase.
