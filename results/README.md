# results/

Pre-rendered transcripts of game runs. These are **committed** to the
repo so visitors can read the interesting output without spending
money on API calls.

Each run lands as a directory:

- `transcript.jsonl` — structured event log (one event per line, the source of truth)
- `report.md`        — human-readable markdown postmortem rendered from the JSONL
- `<short-phase>.svg` — one map image per phase (e.g. `S1901M.svg`)
- `index.html` + one `<short-phase>.html` per phase — slideshow viewer with
  prev/next navigation between phases. **Easiest entry point**: open
  `index.html` and click through the phases.

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

Open `results/20260524T034819Z/index.html` to flip through the maps and
dialogue phase by phase.

### `20260524T031616Z/` — no-negotiation baseline (for comparison)

Same setup, same personas, but agents act independently each turn
with no inter-agent dialogue. Useful as the "what does dialogue
actually buy us?" comparison run. 7 phases, ~$0.35.

Open `results/20260524T031616Z/index.html` for the slideshow view.
