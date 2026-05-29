"""Command-line entry point: run a Diplomacy game end-to-end.

Usage:
    python -m diplomacy_a2a [options]

Runs one full game with the given settings and writes all artifacts
(transcript, maps, slideshow, report) under `results/<run-id>/`. Reads
`ANTHROPIC_API_KEY` from `.env` automatically.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from diplomacy_a2a.config import DEFAULT_MODEL, SMOKE_MODEL


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m diplomacy_a2a",
        description="Run a single Diplomacy game; artifacts land in results/<run-id>/.",
    )
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Anthropic model id (default: {DEFAULT_MODEL})")
    p.add_argument("--years", type=int, default=2,
                   help="how many game-years to play (default: 2)")
    p.add_argument("--rounds", type=int, default=3, dest="negotiation_rounds",
                   help="negotiation rounds before each movement phase (default: 3)")
    p.add_argument("--results-dir", default="results", type=Path,
                   help="root directory for artifacts (default: results/)")
    p.add_argument("--log-prompts", action="store_true",
                   help="also dump each agent's exact prompt+response to "
                        "prompts.jsonl / prompts.md")
    p.add_argument("--log-prompts-years", type=int, default=1,
                   help="when --log-prompts is on, only log the first N years "
                        "(default: 1; keeps the artifact focused on opening play)")
    p.add_argument("--strategy", action="store_true",
                   help="have each agent state a 1-2 sentence strategy before negotiation "
                        "and revise it after, exposing their own history across turns "
                        "(roughly +25-35%% cost; movement phases only)")
    p.add_argument("--upgrade", action="append", default=[], metavar="POWER=MODEL",
                   help="override the model used by one power (repeatable). Example: "
                        "--upgrade TURKEY=claude-sonnet-4-6 in an otherwise Haiku game. "
                        "Plumbing for the axis-A controlled experiment.")
    p.add_argument("--smoke", action="store_true",
                   help=f"cheap-mode shortcut: use {SMOKE_MODEL}, 1 year, 1 round")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the verbose phase-by-phase trace")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)

    # Smoke mode overrides cost-driving knobs to "cheap and small".
    model = args.model
    years = args.years
    rounds = args.negotiation_rounds
    if args.smoke:
        model, years, rounds = SMOKE_MODEL, 1, 1

    # Parse --upgrade POWER=MODEL entries into per-power client overrides.
    power_clients = {}
    upgrade_specs: list[tuple[str, str]] = []
    for spec in args.upgrade:
        if "=" not in spec:
            raise SystemExit(f"--upgrade expects POWER=MODEL, got {spec!r}")
        pw, mdl = spec.split("=", 1)
        upgrade_specs.append((pw.strip().upper(), mdl.strip()))

    # Lazy-import so `--help` works without an API key or the LLM SDK setup.
    load_dotenv(".env")
    from diplomacy_a2a.llm.anthropic_client import AnthropicClient
    from diplomacy_a2a.runner import run_game

    for pw, mdl in upgrade_specs:
        power_clients[pw] = AnthropicClient(model=mdl)

    run_game(
        client=AnthropicClient(model=model),
        model=model,
        years=years,
        negotiation_rounds=rounds,
        results_root=args.results_dir,
        verbose=not args.quiet,
        log_prompts=args.log_prompts,
        log_prompts_years=args.log_prompts_years,
        enable_strategy=args.strategy,
        power_clients=power_clients or None,
    )
