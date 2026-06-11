#!/usr/bin/env python3
"""LLM-capability axis (Axis A): a 7-game rotation.

Three test models, Opus (frontier), Haiku (small Claude), and MiMo (budget),
each rotate through all seven powers once, against a field of the default
(mid-tier) Sonnet. Because every power plays each test role exactly once, board
position is counterbalanced out, and each test model is measured against the
same Sonnet field. Opus and Haiku sit on opposite sides of the board (Haiku
inherits the far-from-Opus seat); MiMo is placed to stay clear of Opus where the
rotation allows, so the frontier reference mostly meets the field.

Runs sequentially, one `python -m diplomacy_a2a run` subprocess per game, for
process isolation (a crash stops the sweep cleanly instead of corrupting it).
Re-running the script skips games whose (Opus, Haiku, MiMo) assignment already
finished, so it resumes where it left off. Use --smoke for a single 1-year game
to scratch/.

    caffeinate -i python experiments/llm_axis.py            # full 7-game sweep
    caffeinate -i python experiments/llm_axis.py --smoke    # 1-year game 1 only
    python experiments/llm_axis.py --dry-run                # print commands, run nothing

Roster is pinned in config.py (LLM_AXIS_TOPSHELF / LLM_AXIS_HAIKU /
LLM_AXIS_LOWCOST; the field is DEFAULT_MODEL). See
results/model-capability/findings.md for the writeup.
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
    LLM_AXIS_HAIKU,
    LLM_AXIS_LOWCOST,
    LLM_AXIS_TOPSHELF,
)

POWERS = {"AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY"}

# The test models, in the column order of ROTATION below: (label, model id).
TEST_MODELS = (
    ("Opus", LLM_AXIS_TOPSHELF),
    ("Haiku", LLM_AXIS_HAIKU),
    ("MiMo", LLM_AXIS_LOWCOST),
)

# (Opus power, Haiku power, MiMo power) per game. A balanced 3x7 Latin
# rectangle: each test model is each power exactly once, and the three never
# collide within a game. Opus and Haiku reuse the original two-model derangement
# (so they stay far apart); MiMo fills a third seat among the Sonnet field,
# placed to avoid bordering Opus in 5 of the 7 games.
ROTATION = [
    ("TURKEY", "GERMANY", "FRANCE"),
    ("GERMANY", "ITALY", "TURKEY"),
    ("ENGLAND", "AUSTRIA", "ITALY"),
    ("AUSTRIA", "FRANCE", "ENGLAND"),
    ("RUSSIA", "ENGLAND", "AUSTRIA"),
    ("ITALY", "RUSSIA", "GERMANY"),
    ("FRANCE", "TURKEY", "RUSSIA"),
]


def _check_balanced(rotation: list[tuple[str, ...]]) -> None:
    """Guard the rotation's experimental validity before spending money: each
    test model plays every power exactly once, and the test models occupy
    distinct powers within each game."""
    assert all(len(g) == len(TEST_MODELS) for g in rotation), \
        f"each game must assign all {len(TEST_MODELS)} test models"
    for col, (label, _) in enumerate(TEST_MODELS):
        powers = [g[col] for g in rotation]
        assert set(powers) == POWERS and len(powers) == len(POWERS), \
            f"{label} must play each power exactly once"
    for g in rotation:
        assert len(set(g)) == len(g), \
            f"test models must occupy distinct powers within a game: {g}"


def _completed_assignments(category_dir: Path) -> set[tuple[str, ...]]:
    """(Opus power, Haiku power, MiMo power) assignments already finished under
    category_dir, recovered from each run's run_started.power_models plus a
    run_ended marker. Lets a re-run skip games it already played.
    """
    done: set[tuple[str, ...]] = set()
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
        assignment = []
        for _, mid in TEST_MODELS:
            powers = [p for p, m in power_models.items() if m == mid]
            assignment.append(powers[0] if len(powers) == 1 else None)
        if all(assignment):
            done.add(tuple(assignment))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the LLM-capability axis (7-game, 3-test-model rotation).")
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
    done = set() if args.smoke else _completed_assignments(category_dir)
    if done:
        print(f"Resuming: {len(done)}/{len(games)} game(s) already complete; "
              f"skipping those.")

    roster = " | ".join(f"{label}: {mid}" for label, mid in TEST_MODELS)
    print(f"Field model: {DEFAULT_MODEL} | {roster}")

    for i, assignment in enumerate(games, 1):
        seats = "  ".join(f"{label}={power}"
                          for (label, _), power in zip(TEST_MODELS, assignment))
        label = f"game {i}/{len(games)}  {seats}"
        if assignment in done:
            print(f"== SKIP {label} (already complete) ==")
            continue
        cmd = [
            sys.executable, "-m", "diplomacy_a2a", "run",
            "--model", DEFAULT_MODEL,
        ]
        for (_, mid), power in zip(TEST_MODELS, assignment):
            cmd += ["--power-model", f"{power}={mid}"]
        cmd += [
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
