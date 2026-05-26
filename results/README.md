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

The three runs below form a progression — **no dialogue → one round → three
rounds** — so you can see what each layer of negotiation buys.

### `20260526T231112Z/` — **3-round negotiation** (current canonical demo)

Seven Sonnet-backed agents, 2 years, with **three rounds** of private pairwise
messaging before each movement phase — and the agents are told the protocol, so
they probe in round 1, negotiate in round 2, and close deals in round 3. 7 phases,
~$2.20, ~23 minutes.

The extra rounds produce explicit, multi-step deal-making and openly telegraphed
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

### `20260524T034819Z/` — 1-round negotiation (for comparison)

Same setup but only **one round** of messaging per movement phase. 7 phases,
~$0.88. Useful for seeing how much the extra rounds deepen the dialogue.

- **Italy → Austria** in S1901M: "I'd like to propose a friendly opening
  between us — I have no designs on Trieste." **Italy's actual orders** in
  F1901M then moved on Trieste — a CICERO-flavored stab, but unannounced.

[**View this run's slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260524T034819Z/index.html)
(GitHub Pages).

### `20260524T031616Z/` — no-negotiation baseline (for comparison)

Same setup, same personas, but agents act independently each turn
with no inter-agent dialogue. Useful as the "what does dialogue
actually buy us?" comparison run. 7 phases, ~$0.35.

[**View this run's slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260524T031616Z/index.html)
(GitHub Pages).
