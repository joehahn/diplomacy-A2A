"""Structured transcript writer + postmortem renderers.

A game run produces these artifacts under `results/<run-id>/`:
- `transcript.jsonl` — one event per line (machine-readable, the source of truth)
- `report.md`       — human-readable postmortem rendered from the JSONL
- `initial.svg`, `<short-phase>.svg` (orders + arrows), `<short-phase>.result.svg`
   (board after the phase resolved) — map images replayed from the JSONL
- `index.html` + `start.html` + `<short-phase>.html` — slideshow-style viewer
   with prev/next navigation (pure HTML, no JS, opens via `open <file>`)

The JSONL is the canonical record. The maps, markdown, and HTML viewer
are all regenerable from it — maps by replaying the recorded orders
through the adjudicator (deterministic, no API calls) — so we can
re-render postmortems with improved templates without re-running games.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from diplomacy_a2a.narration import narrate_phase

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
.narr { background: #fafafa; border-left: 3px solid #ccd; padding: 8px 14px;
        margin: 10px 0; font-size: 0.9em; }
.narr .nrow { margin: 4px 0; line-height: 1.4; }
.narr .nrow b { display: inline-block; min-width: 78px; }
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


# Outcome words worth flagging in the "What happened" narration. Failures
# (order didn't take effect) render cyan; bad outcomes (unit lost) render red.
_FAIL_WORDS = ("bounced", "void", "no convoy", "support cut", "disrupted")


def _colorize_outcomes(html_text: str) -> str:
    """Bold/color the result annotations inside an (already-escaped) narration line."""

    def _paren(m: "re.Match[str]") -> str:
        inner = m.group(1)
        if any(w in inner for w in _FAIL_WORDS):
            return f"<b class='r-fail'>({inner})</b>"
        return m.group(0)

    out = re.sub(r"\(([^)]*)\)", _paren, html_text)
    out = re.sub(r"(\[dislodged:[^\]]*\])", r"<b class='r-bad'>\1</b>", out)
    # A disband shrinks a power — flag the unit it loses (amber).
    out = re.sub(r"\bdisbands (A|F) ([A-Z/]+)", r"<b class='r-warn'>disbands \1 \2</b>", out)
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

    # Most active threads first (by total message count).
    def _count(rounds: dict) -> int:
        return sum(len(by_sender) for by_sender in rounds.values())

    for key in sorted(threads, key=lambda k: (-_count(threads[k]), k)):
        left, right = key
        cl, cr = POWER_COLORS.get(left, "#777"), POWER_COLORS.get(right, "#777")
        out.append("<div class='thread'>")
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

    Slide layout reflects the natural narrative order — read the talk,
    then see what it produced:

    - Slide 0 (`start.html`): the opening board (no orders), with the
      negotiation that happens *before* the first movement below it.
    - Each phase slide: the orders on top, then two maps (the orders as
      arrows on the start-of-phase board, and the resulting board after
      adjudication), then the negotiation leading into the *next* movement
      phase at the bottom — teeing up the next slide's reveal.
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
                "title": f"{ph['long']} ({ph['short']})",
                "heading": f"{ph['long']} <code>({ph['short']})</code>",
                "orders": ph["orders"],
                "narration": narrate_phase(valid_orders, results_by_phase.get(ph["short"], {})),
                "commentary": commentary.get(ph["short"], ""),
                "maps": [
                    ("Orders — start positions, arrows show moves", f"{ph['short']}.svg"),
                    ("Result — positions after this phase resolved", f"{ph['short']}.result.svg"),
                ],
                "dialogue_label": "",
                "dialogue": [],
            }
        )
    # Attach each movement phase's negotiation to the slide before it.
    for mi, ph in enumerate(phases):
        if ph["short"].endswith("M"):
            slides[mi]["dialogue"] = dialogue_by_phase.get(ph["short"], [])
            slides[mi]["dialogue_label"] = ph["long"]

    # --- index.html ---
    meta_bits = [f"Model <code>{run_started.get('model', '?')}</code>"]
    if run_ended:
        meta_bits.append(f"{run_ended.get('phases_played', '?')} phases")
        meta_bits.append(f"${run_ended.get('cost_usd', 0):.4f}")
    index_body = [
        f"<h1>Diplomacy A2A — Run <code>{run_id}</code></h1>",
        f"<div class='meta'>{' · '.join(meta_bits)}</div>",
        "<h2>Slides</h2>",
        "<ol class='phases'>",
    ]
    for sl in slides:
        index_body.append(f"  <li><a href='{sl['file']}'>{sl['title']}</a></li>")
    index_body.append("</ol>")
    index_body.append("<h2>Other artifacts</h2>")
    index_body.append("<ul>")
    index_body.append("  <li><a href='report.md'>report.md</a> — full postmortem with reasoning</li>")
    index_body.append("  <li><a href='transcript.jsonl'>transcript.jsonl</a> — raw event log</li>")
    index_body.append("</ul>")
    (out_dir / "index.html").write_text(
        _html_page(title=f"Diplomacy A2A — {run_id}", body="\n".join(index_body))
    )

    # --- per-slide pages ---
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

        maps_html: list[str] = []
        for caption, src in sl["maps"]:
            maps_html.append(f"<h3 class='mapcap'>{caption}</h3>")
            maps_html.append(f"<img class='map' src='{src}' alt='{caption}'>")

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
        # "What happened" narration, with a link that pops the raw orders.
        recap_html: list[str] = []
        if narration_rows:
            recap_html.append("<h2>What happened this phase</h2>")
        if sl["orders"] is not None:
            recap_html.append("<a class='orders-link' href='#orders-modal'>▤ Orders this phase</a>")
        if narration_rows:
            recap_html += ["<div class='narr'>"] + narration_rows + ["</div>"]

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

        body = "\n".join(
            [
                nav,
                f"<h1>{sl['heading']}</h1>",
                *recap_html,
                *maps_html,
                *commentary_html,
                *nego_link_html,
                nav,
                *orders_modal,
            ]
        )
        (out_dir / sl["file"]).write_text(
            _html_page(title=f"{sl['title']} — {run_id}", body=body)
        )
