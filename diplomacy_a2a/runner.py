"""Run one full game end-to-end.

Orchestrates: state setup, agent calls per phase, validation, submission,
map rendering, transcript logging, postmortem rendering. v1 has no
negotiation phase yet — agents act independently each turn.

Produces under `results/<run-id>/`:
- `transcript.jsonl` — structured event log (source of truth)
- `S1901M.svg`, etc. — one map image per phase
- `report.md`       — markdown postmortem, embeds the SVGs

run-id is a UTC timestamp like `20260523T231245Z`.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from diplomacy_a2a.agent import Agent, validate_orders
from diplomacy_a2a.game.state import GameState, POWERS
from diplomacy_a2a.llm.client import LLMClient
from diplomacy_a2a.personas.registry import DEFAULT_PERSONAS
from diplomacy_a2a.transcripts import TranscriptWriter, render_html_viewer, render_markdown

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


def run_game(
    *,
    client: LLMClient,
    model: str,
    years: int = 2,
    personas: dict[str, str] | None = None,
    results_root: Path = Path("results"),
    max_phases: int = 50,  # safety stop
    verbose: bool = True,
) -> Path:
    """Run a full game, save artifacts under results_root/<run-id>/.

    `model` is passed to transcript metadata only — the client itself
    was constructed with whichever model the caller chose.
    Returns the path to the run directory.
    """
    if personas is None:
        personas = DEFAULT_PERSONAS

    run_id = _run_id()
    run_dir = results_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "transcript.jsonl"

    state = GameState.new()
    agents = {p: Agent(power=p, persona=personas[p], client=client) for p in POWERS}

    end_year = 1900 + years
    tokens = {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0}
    phases_played = 0
    t0 = time.time()

    with TranscriptWriter(jsonl_path).open() as tw:
        tw.write(
            "run_started",
            run_id=run_id,
            model=model,
            years_target=years,
            personas=personas,
            powers=list(POWERS),
        )

        while not state.is_done and phases_played < max_phases:
            short = state.short_phase
            year = int(short[1:5])
            if year > end_year:
                break

            powers_acting = [p for p in POWERS if state.legal_orders(p)]
            if not powers_acting:
                state.advance()
                continue

            tw.write(
                "phase_started",
                phase=state.phase,
                short_phase=short,
                powers_acting=powers_acting,
            )
            if verbose:
                print(f"=== {state.phase} ({short}) — {len(powers_acting)} acting ===")

            for power in powers_acting:
                result = agents[power].submit_orders(state)
                tokens["input"] += result.chat.input_tokens
                tokens["output"] += result.chat.output_tokens
                tokens["cache_create"] += result.chat.cache_creation_input_tokens
                tokens["cache_read"] += result.chat.cache_read_input_tokens

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
                    badge = "" if not invalid else f"  (filtered {len(invalid)} invalid)"
                    print(f"  {power}: {valid}{badge}")

            # Render this phase's map WITH order arrows BEFORE advancing.
            # That captures intent (move/support/convoy arrows visible).
            svg_path = run_dir / f"{short}.svg"
            svg_path.write_text(state.game.render(incl_orders=True, incl_abbrev=False))
            tw.write("phase_rendered", phase=short, svg_path=svg_path.name)

            state.advance()
            phases_played += 1

            tw.write(
                "phase_resolved",
                next_phase=state.short_phase,
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

    # Render the markdown postmortem and the HTML slideshow viewer
    render_markdown(jsonl_path, run_dir / "report.md")
    render_html_viewer(jsonl_path, run_dir)

    if verbose:
        elapsed = time.time() - t0
        print()
        print(f"Run complete: {phases_played} phases in {elapsed:.1f}s, ~${_estimate_cost(tokens):.4f}")
        print(f"Artifacts: {run_dir}")

    return run_dir
