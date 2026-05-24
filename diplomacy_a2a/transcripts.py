"""Structured transcript writer + markdown postmortem renderer.

A game run produces three things under `results/<run-id>/`:
- `transcript.jsonl` — one event per line (machine-readable, the source of truth)
- `report.md`       — human-readable postmortem rendered from the JSONL
- `<short-phase>.svg` — one map image per phase, embedded inline by the markdown

The JSONL is the canonical record. The markdown is regenerable from it,
so we can re-render postmortems with improved templates without
re-running games.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TranscriptWriter:
    """One-event-per-line JSONL writer. Flushes after every write for crash-safety."""

    path: Path
    _fh: TextIO | None = None

    def open(self) -> "TranscriptWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a")
        return self

    def write(self, event_type: str, **fields: Any) -> None:
        assert self._fh is not None, "TranscriptWriter not opened"
        event = {"type": event_type, "ts": _now_iso(), **fields}
        self._fh.write(json.dumps(event, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "TranscriptWriter":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()


def render_markdown(jsonl_path: Path, out_path: Path) -> None:
    """Render the JSONL event log as a human-readable markdown postmortem."""
    events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]

    run_started = next((e for e in events if e["type"] == "run_started"), {})
    run_ended = next((e for e in events if e["type"] == "run_ended"), {})

    lines: list[str] = []
    lines.append(f"# Diplomacy A2A — Run `{run_started.get('run_id', '?')}`")
    lines.append("")
    lines.append(f"- **Model**: `{run_started.get('model', '?')}`")
    lines.append(f"- **Years targeted**: {run_started.get('years_target', '?')}")
    lines.append(f"- **Started**: {run_started.get('ts', '?')}")
    if run_ended:
        lines.append(f"- **Ended**: {run_ended.get('ts', '?')}")
        lines.append(f"- **Phases played**: {run_ended.get('phases_played', '?')}")
        tokens = run_ended.get("tokens", {})
        lines.append(
            f"- **Tokens**: input={tokens.get('input', 0)}, output={tokens.get('output', 0)}, "
            f"cache_create={tokens.get('cache_create', 0)}, cache_read={tokens.get('cache_read', 0)}"
        )
        lines.append(f"- **Approx cost (USD)**: ${run_ended.get('cost_usd', 0):.4f}")
    lines.append("")

    personas = run_started.get("personas", {})
    if personas:
        lines.append("## Personas")
        lines.append("")
        for power, persona in personas.items():
            lines.append(f"- **{power}** — {persona}")
        lines.append("")

    # Walk phase-by-phase. Each phase: phase_started, then alternating
    # agent_response / orders_submitted per power, then phase_rendered.
    current_phase: dict[str, Any] | None = None
    agent_responses: dict[str, dict[str, Any]] = {}
    orders_submitted: dict[str, dict[str, Any]] = {}

    def flush_phase() -> None:
        nonlocal current_phase, agent_responses, orders_submitted
        if current_phase is None:
            return
        short = current_phase.get("short_phase", "?")
        phase_long = current_phase.get("phase", "?")
        lines.append(f"## {phase_long} (`{short}`)")
        lines.append("")
        svg_name = f"{short}.svg"
        # Only embed if file exists alongside (we don't check here — leave to viewer)
        lines.append(f'<img src="{svg_name}" alt="{short} map" width="700">')
        lines.append("")
        # Powers in canonical order if present
        for power, resp in agent_responses.items():
            subs = orders_submitted.get(power, {})
            valid = subs.get("valid", [])
            invalid = subs.get("invalid", [])
            lines.append(f"### {power}")
            if valid:
                lines.append("Orders: " + " · ".join(f"`{o}`" for o in valid))
            else:
                lines.append("Orders: *(none submitted)*")
            if invalid:
                lines.append(f"Invalid (filtered): " + " · ".join(f"`{o}`" for o in invalid))
            text = resp.get("text", "").strip()
            if text:
                # Truncate at ORDERS: for the human-readable reasoning portion
                reasoning = text.split("ORDERS:", 1)[0].strip()
                if reasoning:
                    lines.append("")
                    lines.append("<details><summary>Reasoning</summary>")
                    lines.append("")
                    for rline in reasoning.splitlines():
                        lines.append(f"> {rline}" if rline.strip() else ">")
                    lines.append("")
                    lines.append("</details>")
            lines.append("")
        current_phase = None
        agent_responses = {}
        orders_submitted = {}

    for e in events:
        t = e["type"]
        if t == "phase_started":
            flush_phase()
            current_phase = e
        elif t == "agent_response":
            agent_responses[e["power"]] = e
        elif t == "orders_submitted":
            orders_submitted[e["power"]] = e
        elif t == "phase_resolved":
            # Append resolution summary to the current phase block
            pass
    flush_phase()

    # Final state
    if run_ended:
        lines.append("## Final state")
        lines.append("")
        final = run_ended.get("final_state", {})
        centers = final.get("centers", {})
        if centers:
            lines.append("| Power | Centers | # |")
            lines.append("|---|---|---|")
            for p, cs in sorted(centers.items(), key=lambda kv: -len(kv[1])):
                lines.append(f"| {p} | {', '.join(cs) if cs else '*(none)*'} | {len(cs)} |")
            lines.append("")

    out_path.write_text("\n".join(lines) + "\n")
