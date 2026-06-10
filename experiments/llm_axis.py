#!/usr/bin/env python3
"""LLM-capability axis (Axis A): a 7-game rotation.

A top-shelf model and a low-cost model each rotate through all seven powers
once, on opposite sides of the board, against a field of the default (mid-tier)
model. Because every power plays each test role exactly once, board position is
counterbalanced out, and the two test models are measured against the same
Sonnet field rather than dueling each other.

Runs sequentially, one `python -m diplomacy_a2a run` subprocess per game, for
process isolation (a crash stops the sweep cleanly instead of corrupting it).
Re-running the script skips games whose (top-shelf, low-cost) assignment already
finished, so it resumes where it left off. Use --smoke for a single 1-year game
to scratch/.

    caffeinate -i python experiments/llm_axis.py            # full 7-game sweep
    caffeinate -i python experiments/llm_axis.py --smoke    # 1-year game 1 only
    python experiments/llm_axis.py --dry-run                # print commands, run nothing

Roster is pinned in config.py (LLM_AXIS_TOPSHELF / LLM_AXIS_LOWCOST / the field
is DEFAULT_MODEL). See results/model-capability/findings.md for the writeup.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from diplomacy_a2a.config import (  # noqa: E402
    DEFAULT_MODEL,
    LLM_AXIS_LOWCOST,
    LLM_AXIS_TOPSHELF,
)

POWERS = {"AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY"}

# (top-shelf power, low-cost power) per game. A balanced derangement: each power
# is top-shelf exactly once and low-cost exactly once, and the pair is always
# far apart (never bordering), so each test model meets the Sonnet field rather
# than the other test model.
ROTATION = [
    ("TURKEY", "GERMANY"),
    ("GERMANY", "ITALY"),
    ("ENGLAND", "AUSTRIA"),
    ("AUSTRIA", "FRANCE"),
    ("RUSSIA", "ENGLAND"),
    ("ITALY", "RUSSIA"),
    ("FRANCE", "TURKEY"),
]


def _check_balanced(rotation: list[tuple[str, str]]) -> None:
    """Guard the rotation's experimental validity before spending money."""
    tops = [g[0] for g in rotation]
    lows = [g[1] for g in rotation]
    assert set(tops) == POWERS and len(tops) == len(POWERS), \
        "each power must be top-shelf in exactly one game"
    assert set(lows) == POWERS and len(lows) == len(POWERS), \
        "each power must be low-cost in exactly one game"
    assert all(t != l for t, l in rotation), \
        "top-shelf and low-cost must be different powers within a game"


def _completed_pairs(category_dir: Path) -> set[tuple[str, str]]:
    """(top-shelf power, low-cost power) pairs already finished under
    category_dir, recovered from each run's run_started.power_models plus a
    run_ended marker. Lets a re-run skip games it already played.
    """
    done: set[tuple[str, str]] = set()
    if not category_dir.is_dir():
        return done
    for transcript in category_dir.glob("*/transcript.jsonl"):
        try:
            events = [json.loads(line) for line in
                      transcript.read_text().splitlines() if line.strip()]
        except (OSError, json.JSONDecodeError):
            continue
        started = next((e for e in events if e.get("type") == "run_started"), None)
        ended = any(e.get("type") == "run_ended" for e in events)
        if not started or not ended:
            continue
        power_models = started.get("power_models", {})
        top = [p for p, m in power_models.items() if m == LLM_AXIS_TOPSHELF]
        low = [p for p, m in power_models.items() if m == LLM_AXIS_LOWCOST]
        if len(top) == 1 and len(low) == 1:
            done.add((top[0], low[0]))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the LLM-capability axis (7-game rotation).")
    ap.add_argument("--smoke", action="store_true",
                    help="one 1-year game (rotation[0]) into scratch/, then stop")
    ap.add_argument("--years", type=int, default=10, help="game length (default 10)")
    ap.add_argument("--rounds", type=int, default=3,
                    help="negotiation rounds per phase (default 3)")
    ap.add_argument("--results-dir", default="results",
                    help="results root (default 'results')")
    ap.add_argument("--category", default="model-capability",
                    help="results subfolder (default 'model-capability')")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the commands and exit without running")
    args = ap.parse_args()

    _check_balanced(ROTATION)

    if args.smoke:
        years, results_dir, category, games = 1, "scratch", "", ROTATION[:1]
        print("SMOKE: one 1-year game to scratch/ (no category), then stop.")
    else:
        years, results_dir, category, games = (
            args.years, args.results_dir, args.category, ROTATION)

    category_dir = Path(results_dir) / category if category else Path(results_dir)
    done = set() if args.smoke else _completed_pairs(category_dir)
    if done:
        print(f"Resuming: {len(done)}/{len(games)} game(s) already complete; "
              f"skipping those.")

    print(f"Field model: {DEFAULT_MODEL} | top-shelf: {LLM_AXIS_TOPSHELF} | "
          f"low-cost: {LLM_AXIS_LOWCOST}")

    for i, (top_power, low_power) in enumerate(games, 1):
        label = (f"game {i}/{len(games)}  top={top_power}={LLM_AXIS_TOPSHELF}  "
                 f"low={low_power}={LLM_AXIS_LOWCOST}")
        if (top_power, low_power) in done:
            print(f"== SKIP {label} (already complete) ==")
            continue
        cmd = [
            sys.executable, "-m", "diplomacy_a2a", "run",
            "--model", DEFAULT_MODEL,
            "--power-model", f"{top_power}={LLM_AXIS_TOPSHELF}",
            "--power-model", f"{low_power}={LLM_AXIS_LOWCOST}",
            "--years", str(years),
            "--rounds", str(args.rounds),
            "--results-dir", results_dir,
        ]
        if category:
            cmd += ["--category", category]
        print(f"\n=== {label} ===", flush=True)
        if args.dry_run:
            print("  " + " ".join(cmd))
            continue
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\n!! {label} failed (exit {result.returncode}). Stopping; "
                  f"re-run the script to resume from here.", file=sys.stderr)
            return result.returncode

    print("\n(dry run complete)" if args.dry_run else "\nAll requested games complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
