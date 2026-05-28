"""Run one full game end-to-end.

Orchestrates: state setup, optional negotiation rounds before each
movement phase, agent calls for orders, validation, library
adjudication, map rendering, transcript logging, and final markdown +
HTML postmortem rendering.

Produces under `results/<run-id>/`:
- `transcript.jsonl` — structured event log (source of truth)
- `initial.svg` + `<short-phase>.svg` (orders) + `<short-phase>.result.svg`
  (post-resolution) — maps replayed from the transcript
- `report.md`        — markdown postmortem with dialogue and reasoning
- `index.html` + `start.html` + `<short-phase>.html` — slideshow viewer

run-id is a UTC timestamp like `20260523T231245Z`.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from diplomacy_a2a.agent import Agent, DialogueMessage, validate_orders
from diplomacy_a2a.game.state import GameState, POWERS
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

# Sonnet pricing per million tokens (current published rates).
# Used only for end-of-run cost estimation in the postmortem.
PRICE_PER_MTOK = {
    "input": 3.0,
    "output": 15.0,
    "cache_create": 3.75,
    "cache_read": 0.30,
}


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _estimate_cost(tokens: dict[str, int]) -> float:
    return (
        tokens["input"] * PRICE_PER_MTOK["input"]
        + tokens["output"] * PRICE_PER_MTOK["output"]
        + tokens["cache_create"] * PRICE_PER_MTOK["cache_create"]
        + tokens["cache_read"] * PRICE_PER_MTOK["cache_read"]
    ) / 1_000_000


def _accumulate_tokens(totals: dict[str, int], chat) -> None:
    totals["input"] += chat.input_tokens
    totals["output"] += chat.output_tokens
    totals["cache_create"] += chat.cache_creation_input_tokens
    totals["cache_read"] += chat.cache_read_input_tokens


def run_game(
    *,
    client: LLMClient,
    model: str,
    years: int = 2,
    personas: dict[str, str] | None = None,
    results_root: Path = Path("results"),
    negotiation_rounds: int = 3,  # rounds per MOVEMENT phase (0 = skip)
    max_phases: int = 50,  # safety stop
    verbose: bool = True,
    log_prompts: bool = False,  # also dump full agent prompts to prompts.jsonl
    log_prompts_years: int = 1,  # how many opening years to log when log_prompts is on
) -> Path:
    """Run a full game, save artifacts under results_root/<run-id>/.

    If `log_prompts` is set, the exact prompt each agent receives is written
    to a separate `prompts.jsonl` (system prompt once per power, then the
    per-call user message). Off by default — a full grid of games would
    otherwise produce a lot of large, redundant prompt dumps.
    """
    if personas is None:
        personas = DEFAULT_PERSONAS

    run_id = _run_id()
    run_dir = results_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "transcript.jsonl"

    state = GameState.new()
    agents = {p: Agent(power=p, persona=personas[p], client=client) for p in POWERS}

    prompts_writer = TranscriptWriter(run_dir / "prompts.jsonl").open() if log_prompts else None
    if prompts_writer is not None:
        for p in POWERS:
            prompts_writer.write("agent_system", power=p, system=agents[p]._system)

    end_year = 1900 + years
    tokens = {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0}
    phases_played = 0
    dialogue_history: list[DialogueMessage] = []
    t0 = time.time()

    with TranscriptWriter(jsonl_path).open() as tw:
        tw.write(
            "run_started",
            run_id=run_id,
            model=model,
            years_target=years,
            personas=personas,
            powers=list(POWERS),
            negotiation_rounds=negotiation_rounds,
        )

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
                    )
                    for power, res in results.items():
                        _accumulate_tokens(tokens, res.chat)
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
                            preview = m.text if len(m.text) < 80 else m.text[:77] + "..."
                            print(f"    {m.sender} → {m.recipient}: {preview}")

            # ----- Order phase -----
            for power in powers_acting:
                # Agents receiving dialogue context see their own messages
                # this phase + any history from prior phases.
                result = agents[power].submit_orders(state, dialogue=dialogue_history)
                _accumulate_tokens(tokens, result.chat)
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
            tokens=tokens,
            cost_usd=_estimate_cost(tokens),
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
    # to re-render committed runs, so live and re-rendered output stay identical.
    regenerate_maps(jsonl_path, run_dir)
    render_markdown(jsonl_path, run_dir / "report.md")
    render_html_viewer(jsonl_path, run_dir)

    if verbose:
        elapsed = time.time() - t0
        print()
        print(f"Run complete: {phases_played} phases in {elapsed:.1f}s, ~${_estimate_cost(tokens):.4f}")
        print(f"Artifacts: {run_dir}")

    return run_dir
