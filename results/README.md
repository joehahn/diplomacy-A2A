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

### `20260528T214253Z/` — **3-round negotiation, with strategy log + narration**

Seven Sonnet-backed agents, 2 years, three rounds of private messaging per
movement phase, plus the new `--strategy` flag: each agent writes a 1–2 sentence
**self-authored strategy/goals note** before negotiation begins and a **revised
note** after the final round, with its own strategy history carried into every
later call. Each slide also shows the deterministic narration, the LLM
commentary, and a collapsible **"Agent strategies this phase"** block exposing
each power's plan-vs-revision. 7 phases, **~$3.20**, ~29 minutes. The full
agent-prompt + response dump (`prompts.jsonl` / `prompts.md`) is committed —
see the project README's *Seeing the exact agent prompts*.

Headline highlight (S1901M, Italy):

- **Italy's hidden mind, made visible.** Italy's *initial* strategy note —
  written before negotiation, private to the agent — explicitly says:
  *"I'll court Austria with vague promises while positioning to stab if
  opportunity arises."* Its public message to Austria the same round:
  *"I have no designs on your Balkan centers… I'm planning a quiet opening."*
  After Austria reciprocated, Italy's **revised** strategy note pulled back:
  *"I've agreed with Austria to keep A VEN out of Trieste… I'll honor those
  commitments while pushing aggressively toward the eastern Mediterranean —
  A VEN to TYR keeps pressure on Austria without violating the letter of our
  deal."* Same agent, same turn, two recorded stances — exactly the
  intent-vs-action artifact `--strategy` is built to surface.

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260528T214253Z/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.
