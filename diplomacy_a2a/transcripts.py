"""Structured transcript writer + postmortem renderers.

A game run produces artifacts in two levels under `results/<run-id>/`:

Top level (source of truth, written by runner.py):
- `transcript.jsonl` — one event per line (machine-readable, the source of truth)
- `prompts.jsonl` / `prompts.md` — only if `--log-prompts` is set

`dashboard/` subfolder (rendered from the transcript by the functions here):
- `report.md` — human-readable postmortem rendered from the JSONL
- `initial.svg`, `<short-phase>.svg` (orders + arrows), `<short-phase>.result.svg`
   (board after the phase resolved) — map images replayed from the JSONL
- `index.html` + `start.html` + `<short-phase>.html` — slideshow-style viewer
   with prev/next navigation (pure HTML, no JS, opens via `open <file>`)
- `commentary.json` (if `commentary.py` was run) — viewer reads it if present

The JSONL is the canonical record. The maps, markdown, and HTML viewer
are all regenerable from it — maps by replaying the recorded orders
through the adjudicator (deterministic, no API calls) — so we can
re-render postmortems with improved templates without re-running games.

The renderer functions (`regenerate_maps`, `render_markdown`,
`render_html_viewer`) take an `out_dir` argument that is the dashboard
subfolder; the HTML viewer's links to `transcript.jsonl` and `prompts.md`
use `../` to reach the top-level files.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from diplomacy_a2a.narration import narrate_phase


def _softwrap(text: str, width: int = 78) -> str:
    """Word-wrap long lines so a fenced code block in prompts.md doesn't need
    horizontal scrolling on GitHub. Preserves existing newlines and short lines
    untouched; wraps any line longer than `width` to that width.
    """
    out: list[str] = []
    for line in text.splitlines():
        if len(line) <= width:
            out.append(line)
        else:
            out.append(
                textwrap.fill(
                    line,
                    width=width,
                    break_long_words=False,
                    break_on_hyphens=False,
                    subsequent_indent="  ",
                )
            )
    return "\n".join(out)

# Unit glyphs redrawn as physical-game-style blocks: an Army is a short, fat
# rounded rectangle; a Fleet is a long, narrow one. Each keeps the stock
# viewBox "0 0 23 15" so the library's placement/scaling is unchanged, and
# the body rect has no fill so the per-power CSS class still colors it. The
# dislodged variants use a red outline to flag units that must retreat.
_UNIT_SYMBOLS = {
    "Army": (
        '<symbol id="Army" viewBox="0 0 23 15" overflow="visible"><g>'
        '<rect x="5" y="3" width="15" height="12" rx="2" fill="black" opacity="0.40"/>'
        '<rect x="4" y="1" width="15" height="12" rx="2" stroke="black" stroke-width="1"/>'
        "</g></symbol>"
    ),
    "Fleet": (
        '<symbol id="Fleet" viewBox="0 0 23 15" overflow="visible"><g>'
        '<rect x="1" y="6" width="22" height="7" rx="3.5" fill="black" opacity="0.40"/>'
        '<rect x="0" y="4" width="22" height="7" rx="3.5" stroke="black" stroke-width="1"/>'
        "</g></symbol>"
    ),
    "DislodgedArmy": (
        '<symbol id="DislodgedArmy" viewBox="0 0 23 15" overflow="visible"><g>'
        '<rect x="5" y="3" width="15" height="12" rx="2" fill="black" opacity="0.40"/>'
        '<rect x="4" y="1" width="15" height="12" rx="2" stroke="red" stroke-width="1.5"/>'
        "</g></symbol>"
    ),
    "DislodgedFleet": (
        '<symbol id="DislodgedFleet" viewBox="0 0 23 15" overflow="visible"><g>'
        '<rect x="1" y="6" width="22" height="7" rx="3.5" fill="black" opacity="0.40"/>'
        '<rect x="0" y="4" width="22" height="7" rx="3.5" stroke="red" stroke-width="1.5"/>'
        "</g></symbol>"
    ),
}


def _custom_unit_svg(base_svg: str) -> str:
    """Return the map SVG template with Army/Fleet symbols swapped for blocks."""
    out = base_svg
    for sid, replacement in _UNIT_SYMBOLS.items():
        out = re.sub(rf'<symbol id="{sid}".*?</symbol>', replacement, out, count=1, flags=re.S)
    return out
from typing import Any, TextIO


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TranscriptWriter:
    """One-event-per-line JSONL writer. Flushes after every write for crash-safety.

    Thread-safe: writes are serialized with a lock so concurrent calls from
    worker threads (e.g. API-error loggers firing during a parallel fan-out)
    cannot interleave bytes and corrupt the JSONL.
    """

    path: Path
    _fh: TextIO | None = None
    _lock: "threading.Lock" = field(default_factory=lambda: threading.Lock())

    def open(self) -> "TranscriptWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a")
        return self

    def write(self, event_type: str, **fields: Any) -> None:
        assert self._fh is not None, "TranscriptWriter not opened"
        event = {"type": event_type, "ts": _now_iso(), **fields}
        line = json.dumps(event, default=str) + "\n"
        with self._lock:
            self._fh.write(line)
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "TranscriptWriter":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()


def render_prompts_md(
    prompts_path: Path,
    out_path: Path,
    *,
    transcript_path: Path | None = None,
) -> None:
    """Render `prompts.jsonl` as a readable markdown file.

    The JSONL is one-event-per-line and great for machines but unreadable for
    people (every prompt is a long escaped string). This emits the same
    information as a navigable markdown document: collapsible sections per
    system prompt and per call, grouped by phase / round, so a reader can
    skim the index and expand only the prompts they want to inspect.

    If `transcript_path` is given, each call also shows the **agent's response**
    paired from the transcript (matched by phase/round/kind/power).
    """
    from collections import OrderedDict

    events = [json.loads(line) for line in prompts_path.read_text().splitlines() if line.strip()]
    systems = {e["power"]: e["system"] for e in events if e["type"] == "agent_system"}
    calls = [e for e in events if e["type"] == "agent_prompt"]

    # Pair each call to the response the model produced (from the transcript).
    responses: dict[tuple[str, int, str, str], str] = {}
    if transcript_path is not None and transcript_path.exists():
        for line in transcript_path.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e["type"] == "agent_messages":
                responses[(e["phase"], int(e.get("round", 1)), "negotiate", e["power"])] = e.get("text", "")
            elif e["type"] == "agent_response":
                responses[(e["phase"], 0, "orders", e["power"])] = e.get("text", "")
            elif e["type"] == "agent_strategy":
                responses[(e["phase"], 0, f"strategy_{e['kind']}", e["power"])] = e.get("text", "")

    by_phase: "OrderedDict[str, list[dict]]" = OrderedDict()
    for c in calls:
        by_phase.setdefault(c["phase"], []).append(c)

    run_id = prompts_path.parent.name
    lines: list[str] = []
    lines.append(f"# Agent prompts — `{run_id}`")
    lines.append("")
    lines.append(
        "Readable rendering of `prompts.jsonl` (the JSON Lines source) — what "
        "every agent saw on every call. Each agent receives a **system prompt** "
        "once per game (cached on Anthropic's side via `cache_control: ephemeral`, "
        "so it's billed at ~10% of input price after the first write) and a fresh "
        "**user message** per call (board view, dialogue, instruction). The "
        "sections below are collapsed — click any to expand."
    )
    lines.append("")
    lines.append(f"- **{len(systems)} system prompts** (one per power).")
    lines.append(f"- **{len(calls)} per-call user messages**, grouped by phase.")
    lines.append("")

    # TOC
    lines.append("**Phases:** " + " · ".join(f"[{ph}](#phase-{ph.lower()})" for ph in by_phase))
    lines.append("")

    # System prompts (collapsible)
    lines.append("## System prompts")
    lines.append("")
    for power, sys in systems.items():
        lines.append(f"<details><summary><b>{power}</b> — system prompt</summary>")
        lines.append("")
        lines.append("~~~")
        lines.append(_softwrap(sys))
        lines.append("~~~")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Per-call user prompts
    for ph, ph_calls in by_phase.items():
        lines.append(f'<a id="phase-{ph.lower()}"></a>')
        lines.append(f"## Phase `{ph}`")
        lines.append("")
        nego_by_round: "OrderedDict[int, list[dict]]" = OrderedDict()
        orders: list[dict] = []
        strategy_initial: list[dict] = []
        strategy_revised: list[dict] = []
        for c in ph_calls:
            k = c.get("kind")
            if k == "negotiate":
                nego_by_round.setdefault(c.get("round", 1), []).append(c)
            elif k == "strategy_initial":
                strategy_initial.append(c)
            elif k == "strategy_revised":
                strategy_revised.append(c)
            else:
                orders.append(c)
        def _emit_call(c: dict, summary: str, response_key: tuple) -> None:
            lines.append(f"<details><summary>{summary}</summary>")
            lines.append("")
            lines.append("**Prompt (user message):**")
            lines.append("")
            lines.append("~~~")
            lines.append(_softwrap(c["prompt"]))
            lines.append("~~~")
            lines.append("")
            resp = responses.get(response_key)
            if resp:
                lines.append("**Response:**")
                lines.append("")
                lines.append("~~~")
                lines.append(_softwrap(resp))
                lines.append("~~~")
                lines.append("")
            lines.append("</details>")
            lines.append("")

        if strategy_initial:
            lines.append("### Strategy (initial)")
            lines.append("")
            for c in strategy_initial:
                _emit_call(
                    c,
                    f"<b>{c['power']}</b> — strategy (initial)",
                    (ph, 0, "strategy_initial", c["power"]),
                )
        for rnd in sorted(nego_by_round):
            lines.append(f"### Round {rnd} negotiation")
            lines.append("")
            for c in nego_by_round[rnd]:
                _emit_call(
                    c,
                    f"<b>{c['power']}</b> — negotiate (round {rnd})",
                    (ph, rnd, "negotiate", c["power"]),
                )
        if strategy_revised:
            lines.append("### Strategy (revised)")
            lines.append("")
            for c in strategy_revised:
                _emit_call(
                    c,
                    f"<b>{c['power']}</b> — strategy (revised)",
                    (ph, 0, "strategy_revised", c["power"]),
                )
        if orders:
            lines.append("### Orders")
            lines.append("")
            for c in orders:
                _emit_call(
                    c,
                    f"<b>{c['power']}</b> — orders",
                    (ph, 0, "orders", c["power"]),
                )

    out_path.write_text("\n".join(lines) + "\n")


def regenerate_maps(jsonl_path: Path, out_dir: Path) -> None:
    """Replay the recorded orders through the library to (re)render all map SVGs.

    Adjudication is deterministic given orders, so replaying the `valid`
    orders captured in the JSONL reproduces the exact board states of the
    original run — no LLM calls, no cost. For each phase we emit two maps,
    plus one initial board:

    - `initial.svg`        — opening position, no orders/arrows
    - `<short>.svg`        — start-of-phase positions + that phase's order arrows
    - `<short>.result.svg` — positions after the phase resolved, no arrows

    This is the single source of map generation, shared by live runs
    (`runner.py`) and after-the-fact re-rendering of committed transcripts.
    """
    # Lazy import: keep the game/adjudicator dependency out of the module's
    # import path so plain JSONL→markdown/HTML rendering stays dependency-light.
    import diplomacy
    from diplomacy.engine.renderer import Renderer

    from diplomacy_a2a.game.state import GameState

    events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]

    # Spine of the replay: the phases in playback order, each with the
    # valid orders actually submitted per power.
    phase_order: list[str] = []
    orders_by_phase: dict[str, dict[str, list[str]]] = {}
    for e in events:
        if e["type"] == "phase_started":
            short = e.get("short_phase", "?")
            phase_order.append(short)
            orders_by_phase.setdefault(short, {})
        elif e["type"] == "orders_submitted":
            orders_by_phase.setdefault(e["phase"], {})[e["power"]] = e.get("valid", [])

    out_dir.mkdir(parents=True, exist_ok=True)
    state = GameState.new()

    # Render with our physical-game-style unit blocks: build a one-off SVG
    # template (stock map + redefined Army/Fleet symbols) and bind a Renderer
    # to it. incl_abbrev=True labels each province with its code.
    svg_dir = Path(diplomacy.__file__).parent / "maps" / "svg"
    base_svg = (svg_dir / f"{state.game.map.root_map}.svg").read_text()
    tmp = tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False)
    tmp.write(_custom_unit_svg(base_svg))
    tmp.close()
    state.game.renderer = Renderer(state.game, svg_path=tmp.name)

    try:
        (out_dir / "initial.svg").write_text(
            state.game.render(incl_orders=False, incl_abbrev=True)
        )
        for short in phase_order:
            # Skip any interstitial phases the original run had no orders for
            # (the runner advances past phases with no orderable powers without
            # logging them). Guard against runaway loops.
            for _ in range(10):
                if state.short_phase == short:
                    break
                state.advance()
            else:
                raise RuntimeError(f"Replay could not reach phase {short!r}")

            for power, orders in orders_by_phase.get(short, {}).items():
                state.submit(power, orders)
            (out_dir / f"{short}.svg").write_text(
                state.game.render(incl_orders=True, incl_abbrev=True)
            )
            state.advance()
            (out_dir / f"{short}.result.svg").write_text(
                state.game.render(incl_orders=False, incl_abbrev=True)
            )
    finally:
        os.unlink(tmp.name)


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
    phase_results: dict[str, list[str]] = {}  # unit -> result tokens, for this phase

    def flush_phase() -> None:
        nonlocal current_phase, agent_responses, orders_submitted, dialogue_events, phase_results
        if current_phase is None:
            return
        short = current_phase.get("short_phase", "?")
        phase_long = current_phase.get("phase", "?")
        lines.append(f"## {phase_long} (`{short}`)")
        lines.append("")
        svg_name = f"{short}.svg"
        lines.append(f'<img src="{svg_name}" alt="{short} map" width="700">')
        lines.append("")
        # Plain-English recap of what each power did and how it resolved.
        valid_by_power = {p: s.get("valid", []) for p, s in orders_submitted.items()}
        narration = narrate_phase(valid_by_power, phase_results)
        if narration:
            lines.append("### What happened")
            lines.append("")
            for power, text in narration:
                lines.append(f"- **{power}**: {text}")
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
                lines.append(f"Illegal (dropped): " + " · ".join(f"`{o}`" for o in invalid))
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
        phase_results = {}

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
        elif t == "phase_resolved" and e.get("resolved_phase"):
            phase_results = e.get("results", {})
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
table.settings { border-collapse: collapse; margin: 6px 0 20px; font-size: 0.92em; }
table.settings th, table.settings td { padding: 3px 18px 3px 0; text-align: left;
                                       vertical-align: top; }
table.settings th { font-weight: 600; color: #555; white-space: nowrap;
                    min-width: 160px; }
table.settings td { color: #222; }
nav { display: flex; justify-content: space-between; align-items: center; margin: 12px 0;
      gap: 8px; }
nav a, nav span { padding: 8px 14px; border-radius: 4px; text-decoration: none;
                   font-size: 0.95em; }
nav a { background: #eef; color: #224; }
nav a:hover { background: #dde; }
nav span.disabled { background: #f5f5f5; color: #bbb; }
img.map { max-width: 100%; border: 1px solid #ddd; }
h3.mapcap { margin: 16px 0 4px 0; font-size: 0.8em; color: #888; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.04em; }
.orders { background: #fafafa; border-left: 3px solid #aac; padding: 10px 14px;
          margin: 12px 0; font-size: 0.9em; }
.orders .power { margin: 4px 0; }
.orders .power b { display: inline-block; min-width: 80px; }
.invalid { color: #c33; }
ol.phases { line-height: 1.8; }
.legend { font-size: 0.78em; color: #666; margin: 6px 0 10px; }
.legend .chip { display: inline-block; padding: 1px 8px; margin: 2px 4px 2px 0;
                border-radius: 10px; color: #fff; font-weight: 600; }
.thread { border-top: 1px solid #eee; padding: 10px 0 6px; }
.thread-head { margin: 6px 0 8px; font-size: 0.98em; font-weight: 700; }
.thread-head .arr { color: #aaa; font-weight: 400; }
.rgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; align-items: start; }
.bubble { padding: 7px 11px; border-radius: 12px; border-top-left-radius: 3px;
          background: #f6f6f8; border: 1px solid #e6e6ec; font-size: 0.9em; }
.bubble.empty { background: none; border: none; }
.bubble .bmeta { font-size: 0.72em; font-weight: 700; margin-bottom: 3px;
                 letter-spacing: 0.02em; }
.bubble .rnd { background: #888; color: #fff; border-radius: 8px; padding: 0 6px;
               margin-left: 6px; font-weight: 700; }
.bubble .btext { color: #222; line-height: 1.35; }
/* Pair filter grid (7x7) at top of negotiation page, plus CSS-only
   filter behavior: when a thread is targeted via URL fragment, the
   :has() rule hides every other thread on the page. Requires :has()
   support (Safari 15.4+, Chrome 105+, Firefox 121+). */
.pair-filter { margin: 14px 0 22px; }
.pair-filter h3 { margin: 0 0 6px; font-size: 0.88em; color: #555;
                  font-weight: 600; }
.pair-filter .hint { font-size: 0.78em; color: #888; margin: 0 0 8px; }
.pair-grid { border-collapse: separate; border-spacing: 2px;
             font-size: 0.78em; }
.pair-grid th, .pair-grid td { padding: 0; text-align: center; }
.pair-grid th { font-weight: 700; color: #555; min-width: 38px;
                padding: 3px 5px; background: #f8f8f8; }
.pair-grid td.diag { background: #f0f0f0; color: #aaa; padding: 4px; }
.pair-grid a { display: block; padding: 5px 8px; background: #eef;
               color: #224; text-decoration: none; border-radius: 3px; }
.pair-grid a:hover { background: #dde; }
.pair-filter .clear { display: inline-block; margin-top: 10px;
                      padding: 5px 12px; background: #f5f5f5; color: #555;
                      border-radius: 4px; text-decoration: none;
                      font-size: 0.85em; }
.pair-filter .clear:hover { background: #eee; }
body:has(.thread:target) .thread { display: none; }
body:has(.thread:target) .thread:target { display: block; }
.kpi-row { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap;
           margin: 10px 0; }
.kpi-svg { flex: 0 1 966px; width: 100%; max-width: 1035px; height: auto;
           background: #fafafa; border: 1px solid #eee; border-radius: 4px; }
.kpi-svg .dot-hit { fill: transparent; pointer-events: all; }
.kpi-svg .dot-wrap:hover circle:nth-child(2) { r: 4.5; }
.kpi-svg .dot-tip { opacity: 0; pointer-events: none; }
.kpi-svg .dot-wrap:hover .dot-tip { opacity: 1; }
.kpi-svg .dot-tip-bg { fill: #222; fill-opacity: 0.92; }
.kpi-svg .dot-tip-text { fill: #fff; font: 11px -apple-system, system-ui, sans-serif; }
.kpi-title { font-size: 11px; fill: #555; font-weight: 600; }
.kpi-axis { stroke: #bbb; stroke-width: 0.6; }
.kpi-tick { font-size: 9px; fill: #888; }
.kpi-axis-label { font-size: 9.5px; fill: #666; font-weight: 500; }
.kpi-legend { flex: 0 0 auto; font-size: 0.78em; line-height: 1.6;
              padding: 6px 10px; background: #fafafa; border: 1px solid #eee;
              border-radius: 4px; }
.kpi-legend .leg-row { display: flex; align-items: center; gap: 6px; }
.kpi-legend .leg-swatch { display: inline-block; width: 14px; height: 8px;
                          border-radius: 2px; flex: 0 0 auto; }
.kpi-legend .leg-label { font-weight: 600; color: #444; }
.narr { background: #fafafa; border-left: 3px solid #ccd; padding: 8px 14px;
        margin: 10px 0; font-size: 0.9em; }
.narr .nrow { margin: 4px 0; line-height: 1.4; }
.narr .nrow > b:first-child { display: inline-block; min-width: 78px; }
.orders-link { display: inline-block; margin: 2px 0 12px; padding: 4px 11px; font-size: 0.85em;
               background: #eef; color: #224; border-radius: 4px; text-decoration: none; }
.orders-link:hover { background: #dde; }
.modal { display: none; position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 20; }
.modal:target { display: block; }
.modal-backdrop { position: fixed; top: 0; right: 0; bottom: 0; left: 0;
                  background: rgba(0, 0, 0, 0.45); }
.modal-card { position: relative; margin: 6vh auto; background: #fff; max-width: 620px;
              max-height: 82vh; overflow: auto; padding: 14px 22px 20px; border-radius: 8px;
              box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3); }
.modal-card h2 { margin-top: 4px; }
.modal-close { position: absolute; top: 6px; right: 14px; font-size: 1.5em; line-height: 1;
               color: #999; text-decoration: none; }
.modal-close:hover { color: #333; }
.commentary { background: #f0f4ff; border-left: 3px solid #7a8fd8; padding: 10px 14px;
              margin: 14px 0; font-size: 0.92em; line-height: 1.5; font-style: italic;
              color: #333; }
.commentary .clabel { font-style: normal; font-weight: 700; font-size: 0.75em;
                      text-transform: uppercase; letter-spacing: 0.05em; color: #5566bb;
                      display: block; margin-bottom: 6px; }
.commentary .clist { margin: 0; padding-left: 20px; }
.commentary .clist li { margin: 5px 0; }
.nego-link { display: inline-block; margin: 14px 0; padding: 9px 16px; font-size: 0.95em;
             font-weight: 600; background: #fff0f6; color: #883366; border: 1px solid #e8b8cf;
             border-radius: 6px; text-decoration: none; }
.nego-link:hover { background: #fde0ec; }
.narr .r-fail { color: #0a8fa8; }
.narr .r-bad { color: #c0392b; }
.narr .r-warn { color: #c77a0a; }
.strategies { background: #fbf6ee; border-left: 3px solid #d8b870; padding: 8px 14px;
              margin: 14px 0; font-size: 0.92em; }
.strategies summary { cursor: pointer; }
.strategies .slist { margin-top: 8px; }
.strategies .srow { padding: 6px 0; border-top: 1px dotted #e8d8b8; }
.strategies .srow:first-child { border-top: none; }
.strategies .srow b { display: inline-block; min-width: 78px; }
.strategies .sline { margin: 3px 0 3px 80px; line-height: 1.4; }
.strategies .stag { display: inline-block; font-size: 0.72em; font-weight: 700;
                    text-transform: uppercase; color: #8a6a2e; min-width: 56px;
                    margin-right: 6px; letter-spacing: 0.04em; }
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


# Per-power colors (roughly the traditional Diplomacy palette), used to tint
# message bubbles and the legend so a reader can track who's speaking.
POWER_COLORS = {
    "AUSTRIA": "#c0392b",  # red
    "ENGLAND": "#2c5fa8",  # navy
    "FRANCE": "#1f8aa8",   # cyan
    "GERMANY": "#555555",  # gray/black
    "ITALY": "#2e8b57",    # green
    "RUSSIA": "#7d3c98",   # purple
    "TURKEY": "#cc8a00",   # gold
}


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kpi_chart(
    title: str,
    series: dict[str, list[float]],
    *,
    ymax: float,
    ylabel: str,
    x_labels: list[str],
    width: int = 420,
    height: int = 240,
) -> str:
    """Render a small no-JS SVG line+dot chart with axis labels. One polyline
    per power (colored from POWER_COLORS) with a marker dot at each data
    point. `ymax` is the y-axis upper bound; ticks are 0, ymax/2, ymax.
    `x_labels` are the per-tick labels (e.g. phase shorts) shown rotated 90°
    below the x axis to avoid overlap.
    """
    n = len(x_labels)
    if n < 2 or n != max(len(v) for v in series.values()):
        return ""
    pad_l, pad_r, pad_t, pad_b = 46, 12, 20, 62
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    xs = [pad_l + i * plot_w / (n - 1) for i in range(n)]
    axis_y = height - pad_b

    # Stable per-power jitter so overlapping series (e.g. multiple powers at
    # 5 SCs) don't completely cover each other. Alphabetical order keeps the
    # offset consistent across charts and across runs.
    sorted_powers = sorted(series.keys())
    n_pow = len(sorted_powers)
    power_idx = {p: i for i, p in enumerate(sorted_powers)}

    def y_for(v: float, power: str = "") -> float:
        v = max(0.0, min(v, ymax))
        base = axis_y - (v / ymax) * plot_h
        if not power or n_pow < 2:
            return base
        jitter = (power_idx[power] - (n_pow - 1) / 2) * 0.9  # ~±3 px over 7 powers
        return base + jitter

    parts: list[str] = [
        f"<svg viewBox='0 0 {width} {height}' class='kpi-svg' "
        f"xmlns='http://www.w3.org/2000/svg'>",
        f"<text x='{width/2:.0f}' y='14' text-anchor='middle' class='kpi-title'>{title}</text>",
        # axes
        f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{axis_y}' class='kpi-axis'/>",
        f"<line x1='{pad_l}' y1='{axis_y}' x2='{width-pad_r}' y2='{axis_y}' class='kpi-axis'/>",
    ]
    # Y ticks: 0, mid, ymax (format integers when the value is whole)
    def _fmt(v: float) -> str:
        if abs(v - round(v)) < 1e-6:
            return str(int(round(v)))
        return f"{v:.2f}"
    for frac in (0.0, 0.5, 1.0):
        v = ymax * frac
        y = y_for(v)
        parts.append(
            f"<line x1='{pad_l-3}' y1='{y:.1f}' x2='{pad_l}' y2='{y:.1f}' class='kpi-axis'/>"
        )
        parts.append(
            f"<text x='{pad_l-5}' y='{y+3:.1f}' text-anchor='end' class='kpi-tick'>{_fmt(v)}</text>"
        )
    # X tick marks + per-phase labels rotated -90° (text reads bottom-to-top)
    for i, lbl in enumerate(x_labels):
        x = xs[i]
        parts.append(
            f"<line x1='{x:.1f}' y1='{axis_y}' x2='{x:.1f}' y2='{axis_y+2}' class='kpi-axis'/>"
        )
        # Anchor at the right edge (text-anchor='end') so after rotate(-90) the
        # last character of the label sits just below the tick and the rest
        # extends downward, reading bottom-to-top when tilted left.
        tx, ty = x, axis_y + 5
        parts.append(
            f"<text x='{tx:.1f}' y='{ty:.1f}' text-anchor='end' class='kpi-tick' "
            f"transform='rotate(-90 {tx:.1f},{ty:.1f})'>{lbl}</text>"
        )
    # Y axis label (rotated, anchored at middle of plot area)
    y_label_cx, y_label_cy = 12, (pad_t + axis_y) / 2
    parts.append(
        f"<text x='{y_label_cx}' y='{y_label_cy:.0f}' text-anchor='middle' "
        f"class='kpi-axis-label' "
        f"transform='rotate(-90 {y_label_cx},{y_label_cy:.0f})'>{ylabel}</text>"
    )
    # Lines + dots per power, each offset slightly by a stable per-power jitter
    # so overlapping series don't perfectly cover each other.
    for power in sorted_powers:
        pts = series[power]
        color = POWER_COLORS.get(power, "#777")
        coords = " ".join(
            f"{xs[i]:.1f},{y_for(pts[i], power):.1f}" for i in range(len(pts))
        )
        parts.append(
            f"<polyline points='{coords}' fill='none' stroke='{color}' stroke-width='1.3'/>"
        )
        for i, v in enumerate(pts):
            v_int = int(v) if abs(v - round(v)) < 1e-6 else v
            tip = f"{power.title()}: {v_int}"
            cx = xs[i]
            cy = y_for(v, power)
            # CSS-hover SVG tooltip: the .dot-wrap group catches hover (with an
            # invisible larger hit-circle around the visible dot), the .dot-tip
            # group is opacity 0 by default and opacity 1 on group hover. The
            # native <title> stays as accessibility fallback. Tooltip nudged
            # left if it would overflow the right edge of the plot.
            tip_w = max(60, len(tip) * 6 + 10)
            tip_dx = -tip_w - 10 if cx + tip_w + 14 > width else 8
            tip_dy = -14 if cy < pad_t + 18 else -22
            parts.append(
                f"<g class='dot-wrap'>"
                f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='9' class='dot-hit'/>"
                f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='3.0' "
                f"fill='{color}' stroke='white' stroke-width='0.8'>"
                f"<title>{tip}</title></circle>"
                f"<g class='dot-tip' transform='translate({cx:.1f},{cy:.1f})'>"
                f"<rect x='{tip_dx}' y='{tip_dy}' width='{tip_w}' height='18' "
                f"rx='3' class='dot-tip-bg'/>"
                f"<text x='{tip_dx + 5}' y='{tip_dy + 12}' class='dot-tip-text'>"
                f"{tip}</text></g></g>"
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _kpi_legend(powers: list[str]) -> str:
    rows: list[str] = []
    for p in powers:
        color = POWER_COLORS.get(p, "#777")
        rows.append(
            f"<div class='leg-row'>"
            f"<span class='leg-swatch' style='background:{color}'></span>"
            f"<span class='leg-label'>{p}</span></div>"
        )
    return "<div class='kpi-legend'>" + "".join(rows) + "</div>"


def _kpi_charts_for_phase(
    phase_order: list[str],
    centers_by_phase: dict[str, dict[str, int]],
    up_to: str,
) -> str:
    """Build the SC-count KPI chart + a shared legend for a movement-phase
    slide, showing the running history up to and including `up_to`. Returns
    empty string if there aren't enough points.
    """
    if up_to not in phase_order:
        return ""
    idx = phase_order.index(up_to)
    phases = [p for p in phase_order[: idx + 1] if p in centers_by_phase]
    if len(phases) < 2:
        return ""
    powers = sorted({pw for ph in phases for pw in centers_by_phase[ph].keys()})
    sc_series: dict[str, list[float]] = {p: [] for p in powers}
    for ph in phases:
        c = centers_by_phase[ph]
        for p in powers:
            sc_series[p].append(c.get(p, 0))
    # Dynamic y-axis bound — just above the max observed value, with a floor
    # so the chart doesn't look cramped at the very start of a game.
    sc_max_obs = max(max(pts) for pts in sc_series.values())
    sc_ymax = max(sc_max_obs + 1, 5)
    sc_chart = _kpi_chart(
        "Supply centers", sc_series, ymax=sc_ymax, ylabel="SC", x_labels=phases,
        width=966, height=414,
    )
    legend = _kpi_legend(powers)
    return f"<div class='kpi-row'>{sc_chart}{legend}</div>"


# Coloring in the "What happened" narration:
#   red   (r-bad)  — a unit/right was lost or an order was illegal
#   amber (r-warn) — an order failed to take effect
#   cyan  (r-fail) — coordination actions (support, convoy)
_AMBER_WORDS = ("bounced", "void", "no convoy", "support cut", "disrupted")


def _colorize_outcomes(html_text: str) -> str:
    """Bold/color the result annotations inside an (already-escaped) narration line."""

    def _paren(m: "re.Match[str]") -> str:
        inner = m.group(1)
        if any(w in inner for w in _AMBER_WORDS):
            return f"<b class='r-warn'>({inner})</b>"
        return m.group(0)

    out = re.sub(r"\(([^)]*)\)", _paren, html_text)  # amber: failed orders
    out = re.sub(r"(\[dislodged:[^\]]*\])", r"<b class='r-bad'>\1</b>", out)  # red
    out = re.sub(r"\bdisbands (A|F) ([A-Z/]+)", r"<b class='r-bad'>disbands \1 \2</b>", out)  # red
    out = re.sub(r"\bwaives a build\b", r"<b class='r-bad'>waives a build</b>", out)  # red
    out = re.sub(r"\b(supports|convoys)\b", r"<b class='r-fail'>\1</b>", out)  # cyan
    return out


def _bubble(snd: str, rec: str, rnd: int, text: str) -> str:
    color = POWER_COLORS.get(snd, "#777")
    return (
        f"<div class='bubble' style='border-left:4px solid {color}'>"
        f"<div class='bmeta' style='color:{color}'>{snd} → {rec}"
        f"<span class='rnd'>R{rnd}</span></div>"
        f"<div class='btext'>{_esc(text)}</div></div>"
    )


def _dialogue_threads(label: str, msgs: list[tuple[int, str, str, str]]) -> list[str]:
    """Render the phase's negotiation as per-pair chat threads.

    `msgs` is a list of (round, sender, recipient, text). Messages are
    grouped into bilateral threads (most active first). Within a thread the
    two powers occupy two columns (alphabetically-first on the left), and
    each round is a row — so a round's A→B and B→A messages sit side by
    side, with empty cells where one side stayed silent.
    """
    if not msgs:
        return []
    threads: dict[tuple[str, str], dict[int, dict[str, tuple[str, str]]]] = {}
    for rnd, snd, rec, text in msgs:
        key = tuple(sorted((snd, rec)))
        threads.setdefault(key, {}).setdefault(rnd, {})[snd] = (rec, text)

    present = sorted({p for key in threads for p in key})
    legend = " ".join(
        f"<span class='chip' style='background:{POWER_COLORS.get(p, '#777')}'>{p}</span>"
        for p in present
    )
    out = [f"<h2>Negotiation before {label}</h2>", f"<div class='legend'>{legend}</div>"]

    # 7x7 pair-filter grid. Each cell links to the corresponding pair's
    # thread anchor; the CSS :has() rule collapses the page to that one
    # thread when targeted. "Show all" clears the fragment.
    pair_keys = {tuple(sorted(k)) for k in threads}
    out.append("<div class='pair-filter'>")
    out.append("<h3>Filter to one pair</h3>")
    out.append(
        "<p class='hint'>Click any cell to show only that pair's "
        "conversation. The diagonal cells are each power's own row/column "
        "label.</p>"
    )
    abbrev = {p: p[:3] for p in present}
    out.append("<table class='pair-grid'>")
    out.append("<thead><tr><th></th>" +
               "".join(f"<th>{abbrev[p]}</th>" for p in present) +
               "</tr></thead><tbody>")
    for row in present:
        cells = [f"<th>{abbrev[row]}</th>"]
        for col in present:
            if row == col:
                cells.append("<td class='diag'>—</td>")
            else:
                key = tuple(sorted((row, col)))
                if key in pair_keys:
                    cells.append(f"<td><a href='#pair-{key[0]}-{key[1]}'>·</a></td>")
                else:
                    cells.append("<td class='diag'>—</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    out.append("<a class='clear' href='#'>Show all pairs</a>")
    out.append("</div>")

    # Most active threads first (by total message count).
    def _count(rounds: dict) -> int:
        return sum(len(by_sender) for by_sender in rounds.values())

    for key in sorted(threads, key=lambda k: (-_count(threads[k]), k)):
        left, right = key
        cl, cr = POWER_COLORS.get(left, "#777"), POWER_COLORS.get(right, "#777")
        out.append(f"<div class='thread' id='pair-{left}-{right}'>")
        out.append(
            f"<div class='thread-head'><span style='color:{cl}'>{left}</span>"
            f"<span class='arr'> ⇄ </span>"
            f"<span style='color:{cr}'>{right}</span></div>"
        )
        out.append("<div class='rgrid'>")
        for rnd in sorted(threads[key]):
            by_sender = threads[key][rnd]
            for power in (left, right):  # left column then right column
                if power in by_sender:
                    rec, text = by_sender[power]
                    out.append(_bubble(power, rec, rnd, text))
                else:
                    out.append("<div class='bubble empty'></div>")
        out.append("</div></div>")
    return out


def _orders_block(orders: dict[str, dict[str, Any]]) -> list[str]:
    out = ["<div class='orders'>"]
    for power, ods in orders.items():
        valid_str = " · ".join(f"<code>{o}</code>" for o in ods["valid"]) or "<i>(none)</i>"
        line = f"<div class='power'><b>{power}</b>: {valid_str}"
        if ods["invalid"]:
            inv = " · ".join(f"<code>{o}</code>" for o in ods["invalid"])
            line += f" <span class='invalid'>(illegal: {inv})</span>"
        out.append(line + "</div>")
    out.append("</div>")
    return out


def render_html_viewer(jsonl_path: Path, out_dir: Path) -> None:
    """Generate index.html + one slide per board state under out_dir.

    Each movement-phase slide is self-contained and reads top to bottom
    as the natural flow of a turn: plan, talk, revise, execute, see
    result, interpret.

    - Slide 0 (`start.html`): the opening board only, no orders or
      dialogue.
    - Each phase slide: the orders map (start-of-phase positions with
      move arrows), then the initial strategies collapsible, then the
      link to that phase's negotiation transcript, then the revised
      strategies collapsible, then the result map (board after
      adjudication), then the "what happened" narration and the raw
      orders modal link, then the LLM commentary.
    """
    events = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]

    run_started = next((e for e in events if e["type"] == "run_started"), {})
    run_ended = next((e for e in events if e["type"] == "run_ended"), {})
    run_id = run_started.get("run_id", "?")

    # Per-phase blocks in playback order, plus dialogue keyed by the
    # movement phase it precedes.
    phases: list[dict[str, Any]] = []
    dialogue_by_phase: dict[str, list[tuple[int, str, str, str]]] = {}
    results_by_phase: dict[str, dict[str, list[str]]] = {}  # short -> {unit: [tokens]}
    strategies_by_phase: dict[str, dict[str, dict[str, str]]] = {}  # short -> power -> kind -> text
    centers_by_phase: dict[str, dict[str, int]] = {}  # short -> power -> SC count after this phase
    current: dict[str, Any] | None = None
    for e in events:
        if e["type"] == "phase_started":
            current = {
                "short": e.get("short_phase", "?"),
                "long": e.get("phase", "?"),
                "orders": {},  # power -> {valid, invalid}
            }
            phases.append(current)
            dialogue_by_phase.setdefault(current["short"], [])
        elif e["type"] == "agent_messages":
            for recipient, text in e.get("messages", {}).items():
                dialogue_by_phase.setdefault(e["phase"], []).append(
                    (e.get("round", 1), e["power"], recipient, text)
                )
        elif e["type"] == "phase_resolved" and e.get("resolved_phase"):
            results_by_phase[e["resolved_phase"]] = e.get("results", {})
            centers_by_phase[e["resolved_phase"]] = {
                p: len(cs) for p, cs in e.get("centers", {}).items()
            }
        elif e["type"] == "agent_strategy":
            strategies_by_phase.setdefault(e["phase"], {}).setdefault(e["power"], {})[e["kind"]] = e.get("text", "")
        elif e["type"] == "orders_submitted" and current is not None:
            current["orders"][e["power"]] = {
                "valid": e.get("valid", []),
                "invalid": e.get("invalid", []),
            }

    # Build the ordered slide list. Slide 0 is the opening board; slide k>=1
    # is phases[k-1]. The negotiation before movement phase P is shown on the
    # slide immediately *preceding* P (so it previews the upcoming reveal).
    slides: list[dict[str, Any]] = [
        {
            "file": "start.html",
            "title": "Initial position",
            "heading": "Initial position <small>(opening, before any orders)</small>",
            "orders": None,
            "maps": [("Opening position", "initial.svg")],
            "dialogue_label": "",
            "dialogue": [],
        }
    ]
    # Optional LLM commentary (commentary.py), if it's been generated.
    commentary_path = out_dir / "commentary.json"
    commentary = json.loads(commentary_path.read_text()) if commentary_path.exists() else {}

    for ph in phases:
        valid_orders = {pw: od["valid"] for pw, od in ph["orders"].items()}
        slides.append(
            {
                "file": f"{ph['short']}.html",
                "short": ph["short"],
                "title": f"{ph['long']} ({ph['short']})",
                "heading": f"{ph['long']} <code>({ph['short']})</code>",
                "orders": ph["orders"],
                "narration": narrate_phase(valid_orders, results_by_phase.get(ph["short"], {})),
                "commentary": commentary.get(ph["short"], ""),
                "strategies": strategies_by_phase.get(ph["short"], {}),
                "maps": [
                    ("Orders — start positions, arrows show moves", f"{ph['short']}.svg"),
                    ("Result — positions after this phase resolved", f"{ph['short']}.result.svg"),
                ],
                "dialogue_label": "",
                "dialogue": [],
            }
        )
    # Attach each movement phase's negotiation to the *same* slide as the
    # movement phase it produces. slides[mi + 1] is phases[mi]'s slide
    # because slides[0] is the opening "Initial position" placeholder.
    for mi, ph in enumerate(phases):
        if ph["short"].endswith("M"):
            slides[mi + 1]["dialogue"] = dialogue_by_phase.get(ph["short"], [])
            slides[mi + 1]["dialogue_label"] = ph["long"]

    # --- index.html ---
    # Settings table: what the game was actually configured with.
    default_model = run_started.get("model", "?")
    power_models = run_started.get("power_models") or {}
    settings_rows: list[tuple[str, str]] = []
    # Model line: show overrides if any of the per-power models differ from default
    overrides = sorted(
        (p, m) for p, m in power_models.items() if m != default_model
    )
    if overrides:
        settings_rows.append(("Model (default)", f"<code>{_esc(default_model)}</code>"))
        settings_rows.append((
            "Per-power overrides",
            ", ".join(f"{p}=<code>{_esc(m)}</code>" for p, m in overrides),
        ))
    else:
        settings_rows.append(("Model", f"<code>{_esc(default_model)}</code>"))
    settings_rows.append(("Game years", str(run_started.get("years_target", "?"))))
    settings_rows.append(("Negotiation rounds", str(run_started.get("negotiation_rounds", "?"))))
    has_strategy = any(e.get("type") == "agent_strategy" for e in events)
    settings_rows.append(("Strategy log", "on" if has_strategy else "off"))
    # prompts.{jsonl,md} live at the run-dir top level (out_dir.parent in the
    # current layout where dashboard/ is a subfolder of the run dir).
    prompts_jsonl = out_dir.parent / "prompts.jsonl"
    settings_rows.append((
        "Prompt logging",
        f"on — see <a href='../prompts.md'>prompts.md</a>" if prompts_jsonl.exists() else "off",
    ))
    if run_ended:
        settings_rows.append(("Phases played", str(run_ended.get("phases_played", "?"))))
        elapsed = run_ended.get("elapsed_seconds", 0)
        settings_rows.append(("Wall time", f"{elapsed/60:.1f} min ({elapsed:.0f} s)"))
        # When the game completed (wall-clock UTC at the run_ended event).
        ts = run_ended.get("ts", "")
        if ts:
            try:
                ts_display = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S UTC")
            except (ValueError, TypeError):
                ts_display = ts
            settings_rows.append(("Execution timestamp", ts_display))
        settings_rows.append(("Cost (USD)", f"${run_ended.get('cost_usd', 0):.2f}"))
        # Illegal-orders rate across all movement-phase orders the agents
        # submitted. An illegal order is one the adjudicator rejected as
        # malformed or geometrically impossible (e.g., supporting an attack
        # into a non-adjacent province). Filtered out before resolution.
        total_orders = illegal_orders = 0
        for e in events:
            if e.get("type") == "orders_submitted" and e.get("phase", "").endswith("M"):
                total_orders += len(e.get("valid", [])) + len(e.get("invalid", []))
                illegal_orders += len(e.get("invalid", []))
        if total_orders > 0:
            pct = 100 * illegal_orders / total_orders
            settings_rows.append((
                "Illegal orders",
                f"{illegal_orders} of {total_orders} ({pct:.1f}%)",
            ))
        # Final standings ordered by SC count
        final_centers = run_ended.get("final_state", {}).get("centers", {})
        if final_centers:
            standing = sorted(
                ((p, len(c)) for p, c in final_centers.items()), key=lambda kv: -kv[1]
            )
            settings_rows.append((
                "Final standing",
                " · ".join(f"{p} {n}" for p, n in standing),
            ))
    else:
        settings_rows.append(("Run state", "<i>incomplete (no run_ended event)</i>"))

    settings_html = "<table class='settings'>" + "".join(
        f"<tr><th>{label}</th><td>{value}</td></tr>"
        for label, value in settings_rows
    ) + "</table>"

    index_body = [
        f"<h1>Diplomacy A2A — Run <code>{run_id}</code></h1>",
        "<h2>Game settings</h2>",
        settings_html,
        "<h2>Slides</h2>",
        "<ol class='phases'>",
    ]
    for sl in slides:
        index_body.append(f"  <li><a href='{sl['file']}'>{sl['title']}</a></li>")
    index_body.append("</ol>")
    index_body.append("<h2>Other artifacts</h2>")
    index_body.append("<ul>")
    index_body.append("  <li><a href='report.md'>report.md</a> — full postmortem with reasoning</li>")
    # transcript.jsonl + prompts.* are at the run-dir top level (one level up
    # from the dashboard/ directory the slideshow lives in).
    index_body.append("  <li><a href='../transcript.jsonl'>transcript.jsonl</a> — raw event log</li>")
    if (out_dir.parent / "prompts.md").exists():
        index_body.append(
            "  <li><a href='../prompts.md'>prompts.md</a> — every prompt each agent received "
            "(readable rendering of <code>prompts.jsonl</code>)</li>"
        )
    index_body.append("</ul>")
    (out_dir / "index.html").write_text(
        _html_page(title=f"Diplomacy A2A — {run_id}", body="\n".join(index_body))
    )

    # --- per-slide pages ---
    phase_order = [ph["short"] for ph in phases]
    n = len(slides)
    for i, sl in enumerate(slides):
        prev_link = (
            f"<a href='{slides[i-1]['file']}'>← {slides[i-1]['title']}</a>"
            if i > 0
            else "<span class='disabled'>← prev</span>"
        )
        next_link = (
            f"<a href='{slides[i+1]['file']}'>{slides[i+1]['title']} →</a>"
            if i < n - 1
            else "<span class='disabled'>next →</span>"
        )
        nav = (
            "<nav>"
            f"{prev_link}<a href='index.html'>index ({i+1}/{n})</a>{next_link}"
            "</nav>"
        )

        # Split maps so the orders/opening map can lead the slide and the
        # result map can land after the revised strategies; the new layout
        # reads as plan to talk to revise to execute to result.
        maps_top_html: list[str] = []
        maps_result_html: list[str] = []
        for i, (caption, src) in enumerate(sl["maps"]):
            block = [
                f"<h3 class='mapcap'>{caption}</h3>",
                f"<img class='map' src='{src}' alt='{caption}'>",
            ]
            (maps_result_html if i > 0 else maps_top_html).extend(block)

        narration_rows = []
        for pw, text in (sl.get("narration") or []):
            color = POWER_COLORS.get(pw, "#777")
            body = _colorize_outcomes(_esc(text))
            invalid = (sl.get("orders") or {}).get(pw, {}).get("invalid", [])
            if invalid:
                ill = " · ".join(_esc(o) for o in invalid)
                body += f" <b class='r-bad'>(illegal: {ill})</b>"
            narration_rows.append(
                f"<div class='nrow'><b style='color:{color}'>{pw}</b> {body}</div>"
            )
        # "What happened" narration, with a link that pops the raw orders, and
        # on movement-phase slides a pair of small KPI timeseries (SC count and
        # SoS share) rendered to the right of the narration table.
        recap_html: list[str] = []
        if narration_rows:
            recap_html.append("<h2>What happened this phase</h2>")
        if sl["orders"] is not None:
            recap_html.append("<a class='orders-link' href='#orders-modal'>▤ Orders this phase</a>")
        if narration_rows:
            recap_html.append("<div class='narr'>" + "".join(narration_rows) + "</div>")

        # KPI chart (SC counts over time) lives in its own block, rendered
        # after the commentary; movement-phase slides only.
        kpi_html: list[str] = []
        short = sl.get("short", "")
        if short.endswith("M"):
            charts_html = _kpi_charts_for_phase(phase_order, centers_by_phase, short)
            if charts_html:
                kpi_html.append(charts_html)

        # Raw orders live in a no-JS CSS :target popup, hidden until the link
        # above is clicked.
        orders_modal: list[str] = []
        if sl["orders"] is not None:
            orders_modal = [
                "<div id='orders-modal' class='modal'>",
                "<a class='modal-backdrop' href='#'></a>",
                "<div class='modal-card'>",
                "<a class='modal-close' href='#' title='close'>&times;</a>",
                "<h2>Orders this phase</h2>",
                *_orders_block(sl["orders"]),
                "</div></div>",
            ]

        # Strategies split into two collapsibles so the negotiation link can
        # sit between them. Initial strategies are each power's plan BEFORE
        # the dialogue; revised strategies are the plan AFTER. Empty kinds
        # are skipped so smoke runs and pre-strategy-log runs still render.
        strat = sl.get("strategies") or {}

        def _strategies_block(kind: str, summary: str) -> list[str]:
            out: list[str] = [
                f"<details class='strategies'><summary>{summary}</summary>",
                "<div class='slist'>",
            ]
            for pw in sorted(strat):
                text = strat[pw].get(kind, "")
                if not text:
                    continue
                color = POWER_COLORS.get(pw, "#777")
                out.append(
                    f"<div class='srow'><b style='color:{color}'>{pw}</b>"
                    f"<div class='sline'>{_esc(text)}</div></div>"
                )
            out.append("</div></details>")
            return out

        strategies_initial_html: list[str] = []
        strategies_revised_html: list[str] = []
        if strat and any(s.get("initial") for s in strat.values()):
            strategies_initial_html = _strategies_block(
                "initial",
                "<b>Initial strategies (pre-negotiation)</b>, "
                "each power's self-authored plan before talking.",
            )
        if strat and any(s.get("revised") for s in strat.values()):
            strategies_revised_html = _strategies_block(
                "revised",
                "<b>Revised strategies (post-negotiation)</b>, "
                "each power's updated plan after the negotiation above.",
            )

        commentary_html: list[str] = []
        comm = sl.get("commentary")
        if comm:
            if isinstance(comm, list):
                inner = "<ul class='clist'>" + "".join(f"<li>{_esc(x)}</li>" for x in comm) + "</ul>"
            else:  # back-compat: a single string
                inner = f" {_esc(comm)}"
            commentary_html = [
                f"<div class='commentary'><span class='clabel'>Commentary</span>{inner}</div>"
            ]

        # The negotiation lives on its own child page, reached via a link here.
        nego_link_html: list[str] = []
        if sl["dialogue"]:
            child_file = sl["file"][:-5] + ".negotiation.html"  # strip ".html"
            nego_link_html = [
                f"<a class='nego-link' href='{child_file}'>"
                f"💬 Read the negotiation before {sl['dialogue_label']} →</a>"
            ]
            back = (
                f"<nav><a href='{sl['file']}'>← back to {sl['title']}</a>"
                "<a href='index.html'>index</a></nav>"
            )
            child_body = "\n".join(
                [back, *_dialogue_threads(sl["dialogue_label"], sl["dialogue"]), back]
            )
            (out_dir / child_file).write_text(
                _html_page(title=f"Negotiation — {sl['title']} — {run_id}", body=child_body)
            )

        # Body order follows the natural reading flow of a phase:
        # orders map (plan), initial strategies, negotiation link, revised
        # strategies, result map (outcome), then narration/orders modal/
        # commentary (interpretation), so each slide is self-contained.
        body = "\n".join(
            [
                nav,
                f"<h1>{sl['heading']}</h1>",
                *maps_top_html,
                *strategies_initial_html,
                *nego_link_html,
                *strategies_revised_html,
                *maps_result_html,
                *recap_html,
                *commentary_html,
                *kpi_html,
                nav,
                *orders_modal,
            ]
        )
        (out_dir / sl["file"]).write_text(
            _html_page(title=f"{sl['title']} — {run_id}", body=body)
        )
