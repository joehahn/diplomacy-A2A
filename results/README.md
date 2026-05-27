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

### `20260527T184246Z/` — **3-round negotiation, with turn narration**

Seven Sonnet-backed agents, 2 years, with **three rounds** of private pairwise
messaging before each movement phase — agents are told the protocol, so they
probe in round 1, negotiate in round 2, and close in round 3. Each slide shows a
plain-English **"what happened this phase"** narration beside the maps, that same
recap is fed back to the agents so they reason about prior-turn outcomes, and an
LLM **commentary** block flags threats, cooperation, and betrayals.
8 phases, ~$2.43, ~24 minutes. This run also includes the full agent-prompt dump
(`prompts.jsonl`) — see the project README's *Seeing the exact agent prompts*.

Highlights (F1902M):

- **A double-cross over Belgium** — France reassured Germany with "ceasefire"
  messages, then drove `A PIC → BEL` with Burgundy support and took the center,
  dislodging Germany's fleet. In the *same* round England told France it would
  help, but secretly confirmed to Germany it would support the Belgian hold —
  a final-hour deception caught in the transcript.
- **Turkey collapsing** — its `CON → BUL` and `BLA → BUL` attacks both bounced
  off Austria's supported `A BUL`, Russia drove its fleet out of the Black Sea,
  and it ends the run squeezed to 3 centers despite courting both Rome and Moscow.

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260527T184246Z/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, and dialogue.
