# results/

Game-run artifacts, organized by experiment category so goal-3
controlled-variation grids stay legible as runs accumulate.

## Layout

```
results/
├── canonical/             the published demo runs (committed; see canonical/README.md)
├── axis_a/                model-capability experiments (one stronger model in a homogeneous table)
├── axis_b/                personality-trait experiments
├── axis_c/                memory-depth experiments
├── axis_d/                pre-game-collusion experiments
├── axis_e/                information-asymmetry experiments
└── <run-id>/              category-less runs (the historical layout, still supported)
```

Each subfolder is created on first use by `python -m diplomacy_a2a run
--category <name>`; an empty `--category` writes to `results/<run-id>/`
at the top level (back-compat for any scripted invocations). Throwaway
runs go in `scratch/` (gitignored) rather than here.

## What's in a run directory

Every run directory holds two levels of artifact, separated by
provenance:

**Top level: source of truth, produced live by `run`**

- `transcript.jsonl`: structured event log (one event per line). Every
  other artifact in the directory is deterministically derived from this.
- `prompts.jsonl` / `prompts.md`: only present when the run was launched
  with `--log-prompts`; every agent's exact prompt and response for the
  first `--log-prompts-years` years (default 1).

**`dashboard/`: derived artifacts, produced by `render` and `commentary`**

- `dashboard/report.md`: human-readable markdown postmortem rendered
  from the transcript.
- `dashboard/initial.svg`: the opening board. `dashboard/<short-phase>.svg`:
  that phase's orders as arrows on the start-of-phase board.
  `dashboard/<short-phase>.result.svg`: the board after the phase resolved.
- `dashboard/index.html` + `dashboard/start.html` + one
  `dashboard/<short-phase>.html` per phase: slideshow viewer. Each slide
  reads top to bottom (orders, orders map, resulting board, then the
  negotiation that leads into the next movement phase), so you read the
  talk, then click ahead to see what it produced. **Easiest entry point**:
  open `dashboard/index.html` and click through.
- `dashboard/commentary.json`: strategic interpretation per phase, written
  by `commentary.py` as a post-pass; the viewer reads it if present and
  silently omits the block otherwise.

The split lets you regenerate everything derived with one command
(`rm -rf <run-dir>/dashboard/` then re-run `render`) without any risk to
the irreplaceable LLM output at the top level.

Naming convention for run directories: `YYYYMMDDTHHMMSSZ` (UTC).

## Re-rendering a committed run

The transcript is the source of truth. When the viewer changes (CSS,
narration, KPI charts) re-render in sub-second instead of re-running
the game:

```bash
python -m diplomacy_a2a render results/canonical/<run-id>/                       # no LLM, free
python -m diplomacy_a2a render results/canonical/<run-id>/ --with-commentary     # also refresh commentary if missing
python -m diplomacy_a2a render results/canonical/<run-id>/ --refresh-commentary  # force regenerate commentary
```

`render` is the LLM-free path; `commentary` (or `render --with-commentary`)
adds about $0.03 per phase of Sonnet calls (e.g., ≈$1 / ≈3 min for the
canonical's 33-phase game).

## Where the published demo lives

The current canonical run is committed under `results/canonical/`. See
[`canonical/README.md`](canonical/README.md) for the run-by-run details
and the GitHub Pages dashboard link.
