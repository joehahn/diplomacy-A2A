# results/

Rendered transcripts of game runs. The canonical run is **committed** to the
repo so visitors can read the interesting output without spending money on
API calls; throwaway runs live in `scratch/` (gitignored) instead.

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
- `commentary.json` — strategic interpretation per phase, written by
  `commentary.py` as a post-pass; the viewer reads it if present and silently
  omits the block otherwise.

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Canonical run

### `20260529T225943Z/` — **bare `--log-prompts`, all defaults**

```bash
python -m diplomacy_a2a --log-prompts
```

Sonnet 4.6, 5 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, plus the LLM-commentary post-pass. 18 phases,
**≈$12 / ≈77 min** end-to-end. The full agent-prompt + response dump
(`prompts.jsonl` ≈778 KB / `prompts.md` ≈853 KB) is committed — see the
project README's *Seeing the exact agent prompts*.

Final standings (no eliminations, no solo win — played to the 5-year cap):

| Power | SC count | Centers |
|---|---:|---|
| Germany | 6 | BER, KIE, MUN, DEN, HOL, BEL |
| Russia  | 6 | MOS, SEV, STP, WAR, RUM, SWE |
| Austria | 5 | BUD, VIE, GRE, SER, BUL |
| France  | 5 | BRE, MAR, PAR, POR, SPA |
| Italy   | 5 | NAP, ROM, VEN, TUN, TRI |
| England | 4 | EDI, LON, LVP, NWY |
| Turkey  | 3 | ANK, CON, SMY |

Opening highlight (S1901M, from the LLM commentary):

> *"France moved A PAR → BUR despite telling Germany it was 'purely defensive'
> — Germany accepted this framing, but France now sits one step from Munich
> with a free hand in the west, a position Germany should be watching
> carefully."*

Germany still finished tied-leader at 6 SCs, so the gambit didn't crack the
alliance, but the commentary catches that the public message and the move
didn't quite match — exactly the intent-vs-action artifact `--strategy`
+ `--log-prompts` are built to surface.

[**View this run's turn-by-turn slideshow**](https://joehahn.github.io/diplomacy-A2A/results/20260529T225943Z/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.
