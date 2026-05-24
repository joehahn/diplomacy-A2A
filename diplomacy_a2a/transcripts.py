"""Structured transcript writer + postmortem renderers.

A game run produces these artifacts under `results/<run-id>/`:
- `transcript.jsonl` — one event per line (machine-readable, the source of truth)
- `report.md`       — human-readable postmortem rendered from the JSONL
- `<short-phase>.svg` — one map image per phase, embedded inline by the markdown
- `index.html` + `<short-phase>.html` — slideshow-style viewer with prev/next
   navigation between phases (pure HTML, no JS, opens via `open <file>`)

The JSONL is the canonical record. Both the markdown and the HTML
viewer are regenerable from it, so we can re-render postmortems with
improved templates without re-running games.
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

    # Walk phase-by-phase. Each phase: phase_started, then a mix of
    # agent_messages (negotiation) and agent_response/orders_submitted (orders).
    current_phase: dict[str, Any] | None = None
    agent_responses: dict[str, dict[str, Any]] = {}
    orders_submitted: dict[str, dict[str, Any]] = {}
    dialogue_events: list[dict[str, Any]] = []  # agent_messages events for this phase

    def flush_phase() -> None:
        nonlocal current_phase, agent_responses, orders_submitted, dialogue_events
        if current_phase is None:
            return
        short = current_phase.get("short_phase", "?")
        phase_long = current_phase.get("phase", "?")
        lines.append(f"## {phase_long} (`{short}`)")
        lines.append("")
        svg_name = f"{short}.svg"
        lines.append(f'<img src="{svg_name}" alt="{short} map" width="700">')
        lines.append("")
        # Dialogue (if any messages were exchanged this phase)
        all_msgs = [
            (ev["power"], recipient, text)
            for ev in dialogue_events
            for recipient, text in ev.get("messages", {}).items()
        ]
        if all_msgs:
            lines.append("### Dialogue")
            lines.append("")
            for sender, recipient, text in all_msgs:
                lines.append(f"- **{sender} → {recipient}**: {text}")
            lines.append("")
        # Orders per power
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
        dialogue_events = []

    for e in events:
        t = e["type"]
        if t == "phase_started":
            flush_phase()
            current_phase = e
        elif t == "agent_messages":
            dialogue_events.append(e)
        elif t == "agent_response":
            agent_responses[e["power"]] = e
        elif t == "orders_submitted":
            orders_submitted[e["power"]] = e
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


# ----------------------------------------------------------------------
# HTML viewer (slideshow-style: index.html + one page per phase)
# ----------------------------------------------------------------------

_HTML_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1200px;
       margin: 0 auto; padding: 20px; color: #222; }
h1 { margin: 12px 0 4px 0; font-size: 1.4em; }
h2 { margin: 24px 0 8px 0; font-size: 1.1em; color: #555; }
.meta { color: #777; font-size: 0.9em; margin-bottom: 16px; }
nav { display: flex; justify-content: space-between; align-items: center; margin: 12px 0;
      gap: 8px; }
nav a, nav span { padding: 8px 14px; border-radius: 4px; text-decoration: none;
                   font-size: 0.95em; }
nav a { background: #eef; color: #224; }
nav a:hover { background: #dde; }
nav span.disabled { background: #f5f5f5; color: #bbb; }
img.map { max-width: 100%; border: 1px solid #ddd; }
.orders { background: #fafafa; border-left: 3px solid #aac; padding: 10px 14px;
          margin: 12px 0; font-size: 0.9em; }
.orders .power { margin: 4px 0; }
.orders .power b { display: inline-block; min-width: 80px; }
.invalid { color: #c33; }
ol.phases { line-height: 1.8; }
.dialogue { background: #fff7e6; border-left: 3px solid #d8a; padding: 10px 14px;
            margin: 12px 0; font-size: 0.9em; }
.dialogue .msg { margin: 4px 0; }
.dialogue .who { font-weight: bold; color: #524; }
"""


def _html_page(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html><head>\n"
        f"<meta charset='utf-8'><title>{title}</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head><body>\n"
        f"{body}\n"
        "</body></html>\n"
    )


def render_html_viewer(jsonl_path: Path, out_dir: Path) -> None:
    """Generate index.html + one HTML page per phase under out_dir."""
    events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]

    run_started = next((e for e in events if e["type"] == "run_started"), {})
    run_ended = next((e for e in events if e["type"] == "run_ended"), {})
    run_id = run_started.get("run_id", "?")

    # Group: per-phase blocks in playback order
    phases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for e in events:
        if e["type"] == "phase_started":
            current = {
                "short": e.get("short_phase", "?"),
                "long": e.get("phase", "?"),
                "powers_acting": e.get("powers_acting", []),
                "orders": {},  # power -> {valid, invalid}
                "dialogue": [],  # list of (sender, recipient, text)
            }
            phases.append(current)
        elif e["type"] == "agent_messages" and current is not None:
            for recipient, text in e.get("messages", {}).items():
                current["dialogue"].append((e["power"], recipient, text))
        elif e["type"] == "orders_submitted" and current is not None:
            current["orders"][e["power"]] = {
                "valid": e.get("valid", []),
                "invalid": e.get("invalid", []),
            }

    # --- index.html ---
    meta_bits: list[str] = []
    meta_bits.append(f"Model <code>{run_started.get('model', '?')}</code>")
    if run_ended:
        meta_bits.append(f"{run_ended.get('phases_played', '?')} phases")
        meta_bits.append(f"${run_ended.get('cost_usd', 0):.4f}")
    index_body = [
        f"<h1>Diplomacy A2A — Run <code>{run_id}</code></h1>",
        f"<div class='meta'>{' · '.join(meta_bits)}</div>",
        "<h2>Phases</h2>",
        "<ol class='phases'>",
    ]
    for ph in phases:
        index_body.append(f"  <li><a href='{ph['short']}.html'>{ph['long']} ({ph['short']})</a></li>")
    index_body.append("</ol>")
    index_body.append("<h2>Other artifacts</h2>")
    index_body.append("<ul>")
    index_body.append("  <li><a href='report.md'>report.md</a> — full postmortem with reasoning</li>")
    index_body.append("  <li><a href='transcript.jsonl'>transcript.jsonl</a> — raw event log</li>")
    index_body.append("</ul>")
    (out_dir / "index.html").write_text(
        _html_page(title=f"Diplomacy A2A — {run_id}", body="\n".join(index_body))
    )

    # --- per-phase pages ---
    for i, ph in enumerate(phases):
        prev_link = (
            f"<a href='{phases[i-1]['short']}.html'>← {phases[i-1]['short']}</a>"
            if i > 0
            else "<span class='disabled'>← prev</span>"
        )
        next_link = (
            f"<a href='{phases[i+1]['short']}.html'>{phases[i+1]['short']} →</a>"
            if i < len(phases) - 1
            else "<span class='disabled'>next →</span>"
        )
        nav = (
            "<nav>"
            f"{prev_link}<a href='index.html'>index ({i+1}/{len(phases)})</a>{next_link}"
            "</nav>"
        )
        dialogue_html: list[str] = []
        if ph["dialogue"]:
            dialogue_html.append("<h2>Dialogue this phase</h2>")
            dialogue_html.append("<div class='dialogue'>")
            for sender, recipient, text in ph["dialogue"]:
                # Lightweight HTML-safety: only escape the message body
                safe = (
                    text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                dialogue_html.append(
                    f"<div class='msg'><span class='who'>{sender} → {recipient}:</span> {safe}</div>"
                )
            dialogue_html.append("</div>")

        orders_html: list[str] = ["<div class='orders'>"]
        for power, ods in ph["orders"].items():
            valid_str = " · ".join(f"<code>{o}</code>" for o in ods["valid"]) or "<i>(none)</i>"
            line = f"<div class='power'><b>{power}</b>: {valid_str}"
            if ods["invalid"]:
                inv = " · ".join(f"<code>{o}</code>" for o in ods["invalid"])
                line += f" <span class='invalid'>(filtered: {inv})</span>"
            line += "</div>"
            orders_html.append(line)
        orders_html.append("</div>")

        body = "\n".join(
            [
                nav,
                f"<h1>{ph['long']} <code>({ph['short']})</code></h1>",
                f"<img class='map' src='{ph['short']}.svg' alt='{ph['short']} map'>",
                *dialogue_html,
                "<h2>Orders this phase</h2>",
                *orders_html,
                nav,
            ]
        )
        (out_dir / f"{ph['short']}.html").write_text(
            _html_page(title=f"{ph['short']} — {run_id}", body=body)
        )
