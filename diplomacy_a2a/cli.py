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
                   help=f"Anthropic model id used as the default for all powers "
                        f"(default: {DEFAULT_MODEL})")
    p.add_argument("--years", type=int, default=5,
                   help="how many game-years to play (default: 5)")
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
    p.add_argument("--power-model", action="append", default=[], metavar="POWER=MODEL",
                   help="give one power a different model than the default — either "
                        "weaker (e.g. Haiku) or stronger (e.g. Opus). Repeatable. "
                        "Example: --power-model TURKEY=claude-opus-4-7 while everyone "
                        "else stays on Sonnet. Plumbing for the axis-A controlled "
                        "experiment.")
    p.add_argument("--memory", type=int, default=3, metavar="N",
                   help="default per-agent memory: each agent remembers the last N "
                        "movement turns — covers the 'What happened' narration, the "
                        "agent's own strategy notes, and its visible dialogue history "
                        "(default: 3). Use 0 for a fully memoryless agent.")
    p.add_argument("--power-memory", action="append", default=[], metavar="POWER=N",
                   help="override the memory depth (in movement turns) for one power "
                        "(repeatable). Example: --power-memory TURKEY=10 lets Turkey "
                        "remember 10 turns back while everyone else uses the default.")
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

    # Parse --power-model POWER=MODEL entries into per-power client overrides.
    power_model_specs: list[tuple[str, str]] = []
    for spec in args.power_model:
        if "=" not in spec:
            raise SystemExit(f"--power-model expects POWER=MODEL, got {spec!r}")
        pw, mdl = spec.split("=", 1)
        power_model_specs.append((pw.strip().upper(), mdl.strip()))

    # Parse --power-memory POWER=N entries into per-power memory-depth overrides.
    power_memory: dict[str, int] = {}
    for spec in args.power_memory:
        if "=" not in spec:
            raise SystemExit(f"--power-memory expects POWER=N, got {spec!r}")
        pw, depth = spec.split("=", 1)
        try:
            power_memory[pw.strip().upper()] = int(depth)
        except ValueError:
            raise SystemExit(f"--power-memory N must be an integer, got {depth!r}")

    # Lazy-import so `--help` works without an API key or the LLM SDK setup.
    load_dotenv(".env")
    from diplomacy_a2a.llm.anthropic_client import AnthropicClient, RunnerError
    from diplomacy_a2a.runner import run_game

    power_clients = {pw: AnthropicClient(model=mdl) for pw, mdl in power_model_specs}

    try:
        run_game(
            client=AnthropicClient(model=model),
            model=model,
            years=years,
            negotiation_rounds=rounds,
            results_root=args.results_dir,
            verbose=not args.quiet,
            log_prompts=args.log_prompts,
            log_prompts_years=args.log_prompts_years,
            enable_strategy=True,  # hardwired on
            power_clients=power_clients or None,
            memory=args.memory,
            power_memory=power_memory or None,
        )
    except RunnerError as e:
        import sys
        # Friendly, actionable error message; transcript will lack run_ended
        # (signal of an incomplete run) and api_error events record the failure.
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
