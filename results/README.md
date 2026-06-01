# results/

Rendered transcripts of game runs. The canonical run is **committed** to the
repo so visitors can read the interesting output without spending money on
API calls; throwaway runs live in `scratch/` (gitignored) instead.

Each run lands as a directory with two levels of artifact, separated by
provenance:

**Top level — source of truth, produced by `run`**

- `transcript.jsonl` — structured event log (one event per line). Every
  other artifact in the directory is deterministically derived from this.
- `prompts.jsonl` / `prompts.md` — only present when the run was launched
  with `--log-prompts`; every agent's exact prompt and response for the
  first `--log-prompts-years` years (default 1).

**`dashboard/` — derived artifacts, produced by `render` and `commentary`**

- `dashboard/report.md` — human-readable markdown postmortem rendered
  from the transcript.
- `dashboard/initial.svg` — the opening board; `dashboard/<short-phase>.svg`
  — that phase's orders as arrows on the start-of-phase board;
  `dashboard/<short-phase>.result.svg` — the board after the phase resolved
  (e.g. `dashboard/S1901M.svg` / `dashboard/S1901M.result.svg`).
- `dashboard/index.html` + `dashboard/start.html` + one
  `dashboard/<short-phase>.html` per phase — slideshow viewer. Each slide
  reads top-to-bottom: orders, then the orders map and the resulting board,
  then the negotiation that leads into the *next* movement phase (so you
  read the talk, then click ahead to see what it produced). The opening
  `start.html` shows the initial board and the first round of negotiation.
  **Easiest entry point**: open `dashboard/index.html` and click through.
- `dashboard/commentary.json` — strategic interpretation per phase, written
  by `commentary.py` as a post-pass; the viewer reads it if present and
  silently omits the block otherwise.

The split lets you regenerate everything derived with one command
(`rm -rf results/<run-id>/dashboard/` then re-run `render`) without any
risk to the irreplaceable LLM output at the top level.

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Re-rendering a committed run

The transcript is the source of truth and every other artifact derives from it.
So when the viewer changes (CSS tweaks, narration phrasing, KPI chart updates),
no need to re-run the game — re-render in sub-second:

```bash
python -m diplomacy_a2a render results/<run-id>/                       # no LLM, free
python -m diplomacy_a2a render results/<run-id>/ --with-commentary     # also refresh commentary if missing
python -m diplomacy_a2a render results/<run-id>/ --refresh-commentary  # force regenerate commentary
```

`render` is the LLM-free path; `commentary` (or `render --with-commentary`)
adds about $0.03 per phase of Sonnet calls (e.g., ≈$1 / ≈4 min for a
36-phase game).

## Canonical run

### `20260601T214429Z/`: current canonical (10-year)

```bash
python -m diplomacy_a2a run --log-prompts --with-commentary
```

Sonnet 4.6, 10 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, uniform baseline persona across all 7 powers,
plus the LLM-commentary post-pass. 33 phases, **≈$24 / ≈31 min** (parallel
per-power LLM fan-out).

Final standings at S1911M (no solo win, played to the 10-year cap;
Turkey eliminated at F1906M):

| Power | SC count | Centers |
|---|---:|---|
| Germany | 8 | BEL, BER, DEN, HOL, KIE, MUN, NWY, SWE |
| France  | 6 | BRE, MAR, PAR, POR, SPA, TUN |
| Italy   | 6 | ANK, BUL, NAP, ROM, SMY, VEN |
| Russia  | 6 | CON, MOS, RUM, SEV, STP, WAR |
| Austria | 5 | BUD, GRE, SER, TRI, VIE |
| England | 3 | EDI, LON, LVP |
| Turkey  | 0 | (eliminated) |

Italy occupies Ankara and Smyrna (Turkey's traditional home centers);
Russia holds Constantinople. Germany surges from 2 SCs in F1902M to 8 by
F1910M, becoming the dominant power.

[**View this run's turn-by-turn dashboard**](https://joehahn.github.io/diplomacy-A2A/results/20260601T214429Z/dashboard/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.

### `20260529T225943Z/`: earlier 5-year run, kept as a smaller example

A 5-year Sonnet run with per-power placeholder personas, retained because
it is roughly half the size of the canonical and useful as a quick
visitor example without scrolling through 10 game-years. Final standings
at F1905M were Germany 6 / Russia 6 / Austria 5 / France 5 / Italy 5 /
England 4 / Turkey 3, no eliminations, no dominant power.
