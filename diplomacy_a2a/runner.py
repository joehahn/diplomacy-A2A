"""Run one full game end-to-end.

Orchestrates: state setup, optional negotiation rounds before each
movement phase, agent calls for orders, validation, library
adjudication, map rendering, transcript logging, and final markdown +
HTML postmortem rendering.

Produces under `results/<category>/<run-id>/` (or `results/<run-id>/`
when no category is supplied), in two levels separated by provenance:

Top level (source of truth, produced live during the game):
- `transcript.jsonl` — structured event log
- `prompts.jsonl` / `prompts.md` — only if `--log-prompts` is set

`dashboard/` subfolder (derived at the end of the run via the same
renderers the `render` subcommand uses on committed transcripts):
- `report.md`        — markdown postmortem with dialogue and reasoning
- `initial.svg` + `<short-phase>.svg` (orders) + `<short-phase>.result.svg`
  (post-resolution) — maps replayed from the transcript
- `index.html` + `start.html` + `<short-phase>.html` — slideshow viewer

run-id is a UTC timestamp like `2026-05-23.23.12.45`.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from diplomacy_a2a.agent import Agent, DialogueMessage, StrategyNote, validate_orders
from diplomacy_a2a.game.state import GameState, POWERS
from diplomacy_a2a.llm.anthropic_client import RunnerError
from diplomacy_a2a.llm.client import LLMClient
from diplomacy_a2a.negotiation import run_negotiation_round
from diplomacy_a2a.personas.registry import DEFAULT_PERSONAS
from diplomacy_a2a.transcripts import (
    TranscriptWriter,
    regenerate_maps,
    render_html_viewer,
    render_markdown,
    render_prompts_md,
)

# Per-million-token rates by model family. Used only for end-of-run cost
# estimation. Anthropic rates are published list prices; gateway rates are from
# the OpenRouter model pages (confirmed 2026-06-08). The gateway path sends no
# cache_control, so its cache buckets are always 0 and those rates are nominal.
# Unknown models fall back to the default ("claude-sonnet-4-6") rates so cost is
# over-estimated rather than silently under-estimated.
_RATE_TABLE = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_create": 3.75, "cache_read": 0.30},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0, "cache_create": 18.75, "cache_read": 1.50},
    "claude-opus-4-8":   {"input": 15.0, "output": 75.0, "cache_create": 18.75, "cache_read": 1.50},
    "claude-haiku-4-5":  {"input": 1.0, "output": 5.0, "cache_create": 1.25, "cache_read": 0.10},
    # OpenRouter gateway models (see config.GATEWAY_MODELS).
    "deepseek/deepseek-v4-flash": {"input": 0.0983, "output": 0.1966, "cache_create": 0.0983, "cache_read": 0.0098},
    "google/gemini-3.5-flash":    {"input": 1.50, "output": 9.0, "cache_create": 1.50, "cache_read": 0.15},
    "moonshotai/kimi-k2.6":       {"input": 0.68, "output": 3.42, "cache_create": 0.68, "cache_read": 0.068},
    "qwen/qwen3.5-flash-02-23":   {"input": 0.065, "output": 0.260, "cache_create": 0.065, "cache_read": 0.0065},
    "xiaomi/mimo-v2.5":           {"input": 0.140, "output": 0.280, "cache_create": 0.140, "cache_read": 0.014},
}


def _rates_for(model: str) -> dict[str, float]:
    for key, rates in _RATE_TABLE.items():
        if model.startswith(key):
            return rates
    return _RATE_TABLE["claude-sonnet-4-6"]


# Backwards-compatible alias: any consumers reading PRICE_PER_MTOK get Sonnet rates.
PRICE_PER_MTOK = _RATE_TABLE["claude-sonnet-4-6"]


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d.%H.%M.%S")


def _estimate_cost(tokens_by_model: dict[str, dict[str, int]]) -> float:
    total = 0.0
    for model, tk in tokens_by_model.items():
        rates = _rates_for(model)
        total += (
            tk["input"] * rates["input"]
            + tk["output"] * rates["output"]
            + tk["cache_create"] * rates["cache_create"]
            + tk["cache_read"] * rates["cache_read"]
        )
    return total / 1_000_000


def _empty_bucket() -> dict[str, int]:
    return {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0}


def _accumulate(buckets: dict[str, dict[str, int]], model: str, chat) -> None:
    b = buckets.setdefault(model, _empty_bucket())
    b["input"] += chat.input_tokens
    b["output"] += chat.output_tokens
    b["cache_create"] += chat.cache_creation_input_tokens
    b["cache_read"] += chat.cache_read_input_tokens


_T = TypeVar("_T")


def _fanout(powers: list[str], call: Callable[[str], _T]) -> dict[str, _T]:
    """Run `call(power)` for each power concurrently; return results keyed by power.

    All per-power LLM calls within a phase are independent — they read the
    same `state` / `dialogue` / `strategy_history` snapshot and produce
    per-power results — so a thread pool gives a 3-5× wall-time speedup
    over the previous serial loop. Bookkeeping (transcript writes, token
    accumulation, `state.submit`) stays on the main thread, after this
    returns, in deterministic power order — so transcripts of parallel
    runs remain byte-comparable to serial ones.

    `max_workers=len(powers)` (capped at 7 by the caller's power list) lets
    every acting power's call go out at once. If you hit Anthropic
    rate limits, the AnthropicClient's existing 429-retry path absorbs
    them; dial back the worker count here if it starts hurting wall time.
    """
    if len(powers) <= 1:
        return {p: call(p) for p in powers}
    with ThreadPoolExecutor(max_workers=len(powers)) as ex:
        results = list(ex.map(call, powers))
    return dict(zip(powers, results))


def run_game(
    *,
    client: LLMClient,
    model: str,
    years: int = 10,
    personas: dict[str, str] | None = None,
    results_root: Path = Path("results"),
    category: str = "",  # optional subfolder under results_root (e.g. "canonical", "axis_a")
    negotiation_rounds: int = 3,  # rounds per MOVEMENT phase (0 = skip)
    max_phases: int = 50,  # safety stop
    verbose: bool = True,
    log_prompts: bool = False,  # also dump full agent prompts to prompts.jsonl
    log_prompts_years: int = 1,  # how many opening years to log when log_prompts is on
    enable_strategy: bool = True,  # per-power 1-2 sentence strategy notes (hardwired on)
    power_clients: dict[str, LLMClient] | None = None,  # per-power model overrides (axis A)
    memory: int = 3,  # default per-agent memory: last N movement turns recalled
    power_memory: dict[str, int] | None = None,  # per-power memory overrides
    adjacency_table: bool = True,  # include the standard-map adjacency table in the cached prefix
    render: bool = True,  # also derive maps/report/HTML from the transcript at end
) -> Path:
    """Run a full game, save artifacts under results_root/<run-id>/.

    If `log_prompts` is set, the exact prompt each agent receives is written
    to a separate `prompts.jsonl` (system prompt once per power, then the
    per-call user message). Off by default — a full grid of games would
    otherwise produce a lot of large, redundant prompt dumps.

    `power_clients` lets specific powers use a different LLMClient (and thus
    a different model) — e.g. `{"TURKEY": AnthropicClient("claude-sonnet-4-6")}`
    while the rest use the default `client`. This is the plumbing for the
    axis-A controlled experiment (one stronger model in an otherwise
    homogeneous table).
    """
    if personas is None:
        personas = DEFAULT_PERSONAS
    power_clients = power_clients or {}
    power_memory = power_memory or {}

    run_id = _run_id()
    # With a category (e.g. "canonical", "axis_a"), the run lands under
    # results_root/category/<run-id>/ so goal-3 experiment grids stay
    # organized. Empty category keeps the historical results_root/<run-id>/.
    run_dir = (results_root / category / run_id) if category else (results_root / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "transcript.jsonl"

    state = GameState.new()
    agents = {
        p: Agent(
            power=p,
            persona=personas[p],
            client=power_clients.get(p, client),
            memory=power_memory.get(p, memory),
            adjacency_table=adjacency_table,
        )
        for p in POWERS
    }
    # Per-power model id and memory depth for cost attribution + transcript bookkeeping.
    power_model = {p: getattr(agents[p].client, "model", model) for p in POWERS}
    power_memory_resolved = {p: agents[p].memory for p in POWERS}

    prompts_writer = TranscriptWriter(run_dir / "prompts.jsonl").open() if log_prompts else None
    if prompts_writer is not None:
        for p in POWERS:
            prompts_writer.write("agent_system", power=p, system=agents[p]._system)

    end_year = 1900 + years
    tokens_by_model: dict[str, dict[str, int]] = {}
    phases_played = 0
    dialogue_history: list[DialogueMessage] = []
    strategies_by_power: dict[str, list[StrategyNote]] = {p: [] for p in POWERS}
    t0 = time.time()

    with TranscriptWriter(jsonl_path).open() as tw:
        # Attach an api_error logger to every client (incl. per-power overrides)
        # so retries and final failures land in the transcript for forensics.
        def _attach_logger(power: str, c) -> None:
            if hasattr(c, "set_error_logger"):
                c.set_error_logger(
                    lambda info, p=power: tw.write("api_error", power=p, **info)
                )
        for p in POWERS:
            _attach_logger(p, agents[p].client)

        tw.write(
            "run_started",
            run_id=run_id,
            model=model,
            power_models=power_model,
            power_memory=power_memory_resolved,
            enable_strategy=enable_strategy,
            years_target=years,
            personas=personas,
            powers=list(POWERS),
            negotiation_rounds=negotiation_rounds,
        )

        short = "?"
        while not state.is_done and phases_played < max_phases:
            short = state.short_phase
            year = int(short[1:5])
            if year > end_year:
                break

            # Only capture the first N years of prompts (keeps the artifact
            # focused — opening play is the part worth showing).
            log_this_phase = (
                prompts_writer is not None
                and year <= 1900 + log_prompts_years
            )

            powers_acting = [p for p in POWERS if state.legal_orders(p)]
            if not powers_acting:
                state.advance()
                continue

            is_movement = short.endswith("M")

            tw.write(
                "phase_started",
                phase=state.phase,
                short_phase=short,
                powers_acting=powers_acting,
                is_movement=is_movement,
            )
            if verbose:
                print(f"=== {state.phase} ({short}) — {len(powers_acting)} acting ===")

            # ----- Initial strategy notes (movement phases only) -----
            if is_movement and enable_strategy:
                if verbose:
                    print("  --- Strategy: initial ---")
                strategy_results = _fanout(
                    powers_acting,
                    lambda power: agents[power].state_strategy(
                        state,
                        dialogue=dialogue_history,
                        strategy_history=strategies_by_power[power],
                    ),
                )
                for power in powers_acting:
                    res = strategy_results[power]
                    _accumulate(tokens_by_model, power_model[power], res.chat)
                    note = StrategyNote(phase=short, kind="initial", text=res.text)
                    strategies_by_power[power].append(note)
                    tw.write(
                        "agent_strategy", phase=short, power=power, kind="initial",
                        text=res.text,
                        tokens={
                            "input": res.chat.input_tokens,
                            "output": res.chat.output_tokens,
                            "cache_create": res.chat.cache_creation_input_tokens,
                            "cache_read": res.chat.cache_read_input_tokens,
                        },
                    )
                    if log_this_phase:
                        prompts_writer.write(
                            "agent_prompt", phase=short, kind="strategy_initial",
                            power=power, prompt=res.prompt,
                        )
                    if verbose:
                        print(f"    {power}: {res.text}")

            # ----- Negotiation rounds (movement phases only) -----
            phase_dialogue: list[DialogueMessage] = []
            if is_movement and negotiation_rounds > 0:
                for round_idx in range(negotiation_rounds):
                    if verbose:
                        print(f"  --- Negotiation round {round_idx + 1}/{negotiation_rounds} ---")
                    new_msgs, results = run_negotiation_round(
                        agents=agents,
                        state=state,
                        history=dialogue_history,
                        round_index=round_idx + 1,
                        total_rounds=negotiation_rounds,
                        strategies_by_power=(
                            strategies_by_power if enable_strategy else None
                        ),
                    )
                    for power, res in results.items():
                        _accumulate(tokens_by_model, power_model[power], res.chat)
                        tw.write(
                            "agent_messages",
                            phase=short,
                            round=round_idx + 1,
                            power=power,
                            text=res.chat.text,
                            messages=res.messages,
                            tokens={
                                "input": res.chat.input_tokens,
                                "output": res.chat.output_tokens,
                                "cache_create": res.chat.cache_creation_input_tokens,
                                "cache_read": res.chat.cache_read_input_tokens,
                            },
                        )
                        if log_this_phase:
                            prompts_writer.write(
                                "agent_prompt", phase=short, round=round_idx + 1,
                                kind="negotiate", power=power, prompt=res.prompt,
                            )
                    dialogue_history.extend(new_msgs)
                    phase_dialogue.extend(new_msgs)
                    if verbose:
                        for m in new_msgs:
                            print(f"    {m.sender} → {m.recipient}: {m.text}")

            # ----- Revised strategy notes (after negotiation, before orders) -----
            if is_movement and enable_strategy:
                if verbose:
                    print("  --- Strategy: revised ---")
                strategy_results = _fanout(
                    powers_acting,
                    lambda power: agents[power].revise_strategy(
                        state,
                        dialogue=dialogue_history,
                        strategy_history=strategies_by_power[power],
                    ),
                )
                for power in powers_acting:
                    res = strategy_results[power]
                    _accumulate(tokens_by_model, power_model[power], res.chat)
                    note = StrategyNote(phase=short, kind="revised", text=res.text)
                    strategies_by_power[power].append(note)
                    tw.write(
                        "agent_strategy", phase=short, power=power, kind="revised",
                        text=res.text,
                        tokens={
                            "input": res.chat.input_tokens,
                            "output": res.chat.output_tokens,
                            "cache_create": res.chat.cache_creation_input_tokens,
                            "cache_read": res.chat.cache_read_input_tokens,
                        },
                    )
                    if log_this_phase:
                        prompts_writer.write(
                            "agent_prompt", phase=short, kind="strategy_revised",
                            power=power, prompt=res.prompt,
                        )
                    if verbose:
                        print(f"    {power}: {res.text}")

            # ----- Order phase -----
            # Agents receiving dialogue context see their own messages this
            # phase + any history from prior phases. Calls fan out in
            # parallel; `state.submit` + transcript writes happen serially
            # below so adjudication input is deterministic.
            order_results = _fanout(
                powers_acting,
                lambda power: agents[power].submit_orders(
                    state,
                    dialogue=dialogue_history,
                    strategy_history=(
                        strategies_by_power[power] if enable_strategy else None
                    ),
                ),
            )
            for power in powers_acting:
                result = order_results[power]
                _accumulate(tokens_by_model, power_model[power], result.chat)
                if log_this_phase:
                    prompts_writer.write(
                        "agent_prompt", phase=short, kind="orders",
                        power=power, prompt=result.prompt,
                    )

                valid, invalid = validate_orders(state, power, result.orders)

                tw.write(
                    "agent_response",
                    phase=short,
                    power=power,
                    text=result.chat.text,
                    parsed_orders=result.orders,
                    tokens={
                        "input": result.chat.input_tokens,
                        "output": result.chat.output_tokens,
                        "cache_create": result.chat.cache_creation_input_tokens,
                        "cache_read": result.chat.cache_read_input_tokens,
                    },
                )
                tw.write(
                    "orders_submitted",
                    phase=short,
                    power=power,
                    valid=valid,
                    invalid=invalid,
                )

                state.submit(power, valid)
                if verbose:
                    badge = "" if not invalid else f"  (dropped {len(invalid)} illegal)"
                    print(f"  {power}: {valid}{badge}")

            state.advance()
            phases_played += 1

            # Capture the just-resolved phase's per-unit results (bounce,
            # dislodged, …) so the viewer/report can narrate it from the JSONL.
            resolved = state.game.get_phase_history()[-1]
            tw.write(
                "phase_resolved",
                resolved_phase=resolved.name,
                next_phase=state.short_phase,
                results={u: [str(t) for t in r] for u, r in resolved.results.items()},
                units={p: state.units(p) for p in POWERS},
                centers={p: state.centers(p) for p in POWERS},
            )

        tw.write(
            "run_ended",
            phases_played=phases_played,
            elapsed_seconds=round(time.time() - t0, 1),
            final_state={
                "phase": state.phase,
                "units": {p: state.units(p) for p in POWERS},
                "centers": {p: state.centers(p) for p in POWERS},
            },
            tokens_by_model=tokens_by_model,
            cost_usd=_estimate_cost(tokens_by_model),
        )

    if prompts_writer is not None:
        prompts_writer.close()
        render_prompts_md(
            run_dir / "prompts.jsonl",
            run_dir / "prompts.md",
            transcript_path=jsonl_path,
        )

    # Maps are regenerated from the completed transcript by replaying the
    # recorded orders through the library — the same deterministic path used
    # to re-render committed runs (`python -m diplomacy_a2a render <run-dir>`),
    # so live and re-rendered output stay identical. Set `render=False` to skip
    # this block — useful when you want to call `render` separately, e.g. after
    # generating commentary.
    if render:
        # Derived artifacts (maps, report, HTML slides, commentary if present)
        # land under run_dir/dashboard/. transcript.jsonl + prompts.* stay at
        # the run-dir top level as the source-of-truth artifacts.
        dashboard_dir = run_dir / "dashboard"
        dashboard_dir.mkdir(exist_ok=True)
        regenerate_maps(jsonl_path, dashboard_dir)
        render_markdown(jsonl_path, dashboard_dir / "report.md")
        render_html_viewer(jsonl_path, dashboard_dir)

    if verbose:
        elapsed = time.time() - t0
        print()
        print(f"Run complete: {phases_played} phases in {elapsed:.1f}s, ~${_estimate_cost(tokens_by_model):.4f}")
        print(f"Artifacts: {run_dir}")

    return run_dir
