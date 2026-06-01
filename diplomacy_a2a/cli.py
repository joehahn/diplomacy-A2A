"""Command-line entry point for Diplomacy A2A.

The CLI is organized as three subcommands, split along cost / LLM-use lines:

  run         Execute a game — agents negotiate, agents move, library
              adjudicates. Writes transcript.jsonl (+ prompts.jsonl if
              --log-prompts), auto-renders the dashboard at the end.
              The only command that costs real money. ≈$24 for the
              canonical Sonnet 10-year configuration.

  render      Re-derive the dashboard from a finished transcript: maps,
              report.md, HTML slideshow. No LLM, free, sub-second.
              Use this after tweaking viewer code without re-running games.

  commentary  Generate commentary.json — LLM-written strategic interpretation
              per phase. Modest cost (~$1 on Sonnet for the canonical's 36
              phases). Re-runnable with a different model via --model.

Composition flag — `--with-commentary` (valid on both `run` and `render`)
runs the commentary step then re-renders so the slides include it. This is
the alias for "give me the polished dashboard" without typing two commands.

Back-compat: invoking the module without a subcommand (`python -m diplomacy_a2a
[opts]`) defaults to `run`, so existing scripted invocations keep working.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from diplomacy_a2a.config import DEFAULT_MODEL, SMOKE_MODEL

_SUBCOMMANDS = {"run", "render", "commentary"}


def _add_run_args(p: argparse.ArgumentParser) -> None:
    """Arguments for the `run` subcommand (also the back-compat top-level path)."""
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Anthropic model id used as the default for all powers "
                        f"(default: {DEFAULT_MODEL})")
    p.add_argument("--years", type=int, default=10,
                   help="how many game-years to play (default: 10)")
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
    p.add_argument("--no-adjacency-table", action="store_true",
                   help="omit the standard-map adjacency table from the cached "
                        "system prefix. By default the table is included, "
                        "which reduces support-legality mistakes; turning it "
                        "off forces agents to infer adjacency from the "
                        "legal-moves list and training data (axis-E variant).")
    p.add_argument("--smoke", action="store_true",
                   help=f"cheap-mode shortcut: use {SMOKE_MODEL}, 1 year, 1 round")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the verbose phase-by-phase trace")
    p.add_argument("--no-render", action="store_true",
                   help="skip the dashboard render at end of game (transcript still "
                        "written; run `render` separately to produce maps/HTML).")
    p.add_argument("--with-commentary", action="store_true",
                   help="after the game, also generate LLM commentary and re-render "
                        "so the slides include it. Adds ~$0.50 of Sonnet calls and "
                        "~2 minutes; useful for the canonical published demo.")
    p.add_argument("--commentary-model", default=None, metavar="MODEL",
                   help="model to use for the commentary post-pass when "
                        "--with-commentary is set (default: same as --model).")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m diplomacy_a2a",
        description="Run a Diplomacy game, render its dashboard, or add LLM "
                    "commentary. Invoking with no subcommand defaults to `run`.",
    )
    sub = p.add_subparsers(dest="subcommand", metavar="{run,render,commentary}")

    p_run = sub.add_parser(
        "run",
        help="execute a game (LLM calls; ≈$24 / ≈31 min for the canonical 10-yr Sonnet run)",
        description="Execute a game and (by default) render its dashboard. "
                    "This is the only command that costs real money.",
    )
    _add_run_args(p_run)

    p_render = sub.add_parser(
        "render",
        help="rebuild dashboard from transcript (no LLM, free)",
        description="Re-derive the dashboard (maps, report.md, HTML slideshow) "
                    "from a finished transcript.jsonl. No LLM, sub-second.",
    )
    p_render.add_argument("run_dir", type=Path,
                          help="path to a finished run directory, e.g. "
                               "results/20260529T225943Z/")
    p_render.add_argument("--with-commentary", action="store_true",
                          help="ensure commentary.json is present (generate it if "
                               "missing or refresh it if --refresh-commentary), then "
                               "render so the slides include it.")
    p_render.add_argument("--refresh-commentary", action="store_true",
                          help="regenerate commentary.json even if one already exists "
                               "(implies --with-commentary).")
    p_render.add_argument("--commentary-model", default=DEFAULT_MODEL, metavar="MODEL",
                          help=f"model for the commentary post-pass when "
                               f"--with-commentary is set (default: {DEFAULT_MODEL}).")

    p_comm = sub.add_parser(
        "commentary",
        help="generate commentary.json from transcript (LLM only; ≈$0.50)",
        description="Generate per-phase LLM commentary into commentary.json. "
                    "Does NOT re-render — use `render` afterward (or use "
                    "`render --with-commentary` to do both in one step).",
    )
    p_comm.add_argument("run_dir", type=Path,
                        help="path to a finished run directory")
    p_comm.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Anthropic model id for the commentator "
                             f"(default: {DEFAULT_MODEL})")

    return p


def _parse_kv_list(specs: list[str], flag: str, value_kind: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"{flag} expects POWER={value_kind}, got {spec!r}")
        k, v = spec.split("=", 1)
        out.append((k.strip().upper(), v.strip()))
    return out


def _do_render(run_dir: Path) -> None:
    """Re-derive maps / report.md / HTML slideshow from a finished transcript.

    Derived artifacts land under `run_dir/dashboard/` so the source-of-truth
    files (`transcript.jsonl`, `prompts.*`) stay separated at the top level.
    """
    from diplomacy_a2a.transcripts import (
        regenerate_maps,
        render_html_viewer,
        render_markdown,
    )
    jsonl_path = run_dir / "transcript.jsonl"
    if not jsonl_path.exists():
        raise SystemExit(f"No transcript.jsonl in {run_dir}")
    dashboard_dir = run_dir / "dashboard"
    dashboard_dir.mkdir(exist_ok=True)
    regenerate_maps(jsonl_path, dashboard_dir)
    render_markdown(jsonl_path, dashboard_dir / "report.md")
    render_html_viewer(jsonl_path, dashboard_dir)
    print(f"Rendered: {dashboard_dir}")


def _do_commentary(run_dir: Path, model: str) -> None:
    """Generate commentary.json from a finished transcript. Does not re-render."""
    from diplomacy_a2a.commentary import generate_commentary
    from diplomacy_a2a.llm.anthropic_client import AnthropicClient, RunnerError
    jsonl_path = run_dir / "transcript.jsonl"
    if not jsonl_path.exists():
        raise SystemExit(f"No transcript.jsonl in {run_dir}")
    try:
        commentary = generate_commentary(jsonl_path, AnthropicClient(model=model))
    except RunnerError as e:
        print(f"\nERROR: {e}\n", file=sys.stderr)
        raise SystemExit(1)
    print(f"Commentary: {len(commentary)} phases written to "
          f"{run_dir / 'dashboard' / 'commentary.json'}")


def _run_subcommand(args: argparse.Namespace) -> None:
    """Dispatch the `run` subcommand: game execution + optional render/commentary."""
    # Smoke mode overrides cost-driving knobs to "cheap and small".
    model = args.model
    years = args.years
    rounds = args.negotiation_rounds
    if args.smoke:
        model, years, rounds = SMOKE_MODEL, 1, 1

    power_model_specs = _parse_kv_list(args.power_model, "--power-model", "MODEL")
    power_memory: dict[str, int] = {}
    for pw, depth in _parse_kv_list(args.power_memory, "--power-memory", "N"):
        try:
            power_memory[pw] = int(depth)
        except ValueError:
            raise SystemExit(f"--power-memory N must be an integer, got {depth!r}")

    # Lazy-import so `--help` works without an API key or the LLM SDK setup.
    load_dotenv(".env")
    from diplomacy_a2a.llm.anthropic_client import AnthropicClient, RunnerError
    from diplomacy_a2a.runner import run_game

    power_clients = {pw: AnthropicClient(model=mdl) for pw, mdl in power_model_specs}

    try:
        run_dir = run_game(
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
            adjacency_table=not args.no_adjacency_table,
            render=not args.no_render,
        )
    except RunnerError as e:
        # Friendly, actionable error message; transcript will lack run_ended
        # (signal of an incomplete run) and api_error events record the failure.
        print(f"\nERROR: {e}\n", file=sys.stderr)
        raise SystemExit(1)

    if args.with_commentary:
        commentary_model = args.commentary_model or model
        print()
        print(f"Generating LLM commentary ({commentary_model})…")
        _do_commentary(run_dir, commentary_model)
        # Re-render so the freshly-written commentary.json appears in the slides.
        _do_render(run_dir)


def _render_subcommand(args: argparse.Namespace) -> None:
    """Dispatch the `render` subcommand: rebuild dashboard from transcript."""
    run_dir: Path = args.run_dir
    refresh = args.refresh_commentary
    if args.with_commentary or refresh:
        commentary_json = run_dir / "dashboard" / "commentary.json"
        if refresh or not commentary_json.exists():
            load_dotenv(".env")
            print(f"Generating LLM commentary ({args.commentary_model})…")
            _do_commentary(run_dir, args.commentary_model)
        else:
            print(f"Commentary already present: {commentary_json} "
                  f"(use --refresh-commentary to regenerate)")
    _do_render(run_dir)


def _commentary_subcommand(args: argparse.Namespace) -> None:
    """Dispatch the `commentary` subcommand: write commentary.json (no render)."""
    load_dotenv(".env")
    _do_commentary(args.run_dir, args.model)
    print("(Run `render` to rebuild the HTML slides with this commentary.)")


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    # Back-compat: if no subcommand is given, treat all args as `run` args.
    # Detection: first arg is missing or doesn't match a known subcommand.
    if not argv or argv[0] not in _SUBCOMMANDS:
        # Special-case bare --help / -h at the top level: let argparse show the
        # subcommand-aware top-level help, don't silently route to `run`.
        if argv and argv[0] in ("-h", "--help"):
            _build_parser().parse_args(argv)
            return
        argv = ["run"] + argv

    args = _build_parser().parse_args(argv)
    if args.subcommand == "run":
        _run_subcommand(args)
    elif args.subcommand == "render":
        _render_subcommand(args)
    elif args.subcommand == "commentary":
        _commentary_subcommand(args)
    else:  # pragma: no cover — argparse should never let us reach here
        raise SystemExit(f"unknown subcommand: {args.subcommand!r}")
