#!/usr/bin/env python3
"""Build the LLM-capability-axis cross-game dashboard.

Reads the seven counterbalanced rotation games (Opus and MiMo each rotate
through all seven powers once, against a Sonnet field; see
experiments/llm_axis.py) and aggregates per-model rather than per-power, so
each metric is attributed to the model that drove that power. Emits three
hand-rolled inline-SVG plots plus an index.html into the output dashboard dir.
No plotting dependency, matching the per-game dashboards in transcripts.py.

    python experiments/model_capability/build_axis_dashboard.py \
        --games scratch/model-capability-3yr \
        --out results/model-capability/dashboard

Plots:
  1. final_centers.svg  - final supply centers by model (the ranking)
  2. sc_trajectory.svg  - mean supply centers by year, per model
  3. competence.svg     - illegal-order rate, support-move success, self-bounce
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import re
import statistics
from pathlib import Path

# --- model roster -----------------------------------------------------------

MODEL_LABEL = {
    "claude-opus-4-8": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "xiaomi/mimo-v2.5": "MiMo",
}
# Display order: frontier, field, budget.
ORDER = ["Opus", "Sonnet", "MiMo"]
TIER = {"Opus": "L (frontier)", "Sonnet": "M (field)", "MiMo": "S (budget)"}
COLOR = {"Opus": "#1b5e9b", "Sonnet": "#6b6b6b", "MiMo": "#c85a23"}

# Standard Diplomacy home-center counts, for the year-0 trajectory baseline.
START_CENTERS = {
    "AUSTRIA": 3, "ENGLAND": 3, "FRANCE": 3, "GERMANY": 3,
    "ITALY": 3, "RUSSIA": 4, "TURKEY": 3,
}
BOARD_AVG = 34 / 7  # all 34 supply centers / 7 powers, the no-edge baseline


# --- extraction -------------------------------------------------------------

def _load(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def extract(games_dir: str) -> dict:
    """Aggregate per-model metrics across every rotation game under games_dir."""
    paths = sorted(glob.glob(f"{games_dir}/*/transcript.jsonl"))
    if not paths:
        raise SystemExit(f"no transcripts under {games_dir}")

    final = {m: [] for m in ORDER}                       # final SC per power-game
    traj = collections.defaultdict(lambda: collections.defaultdict(list))  # yr->model->[sc]
    raw = collections.defaultdict(collections.Counter)   # model->counters

    for path in paths:
        events = _load(path)
        power_model = next(e for e in events if e["type"] == "run_started")["power_models"]
        label = {p: MODEL_LABEL[m] for p, m in power_model.items()}

        # final supply centers
        ended = next(e for e in events if e["type"] == "run_ended")
        centers = ended["final_state"]["centers"]
        for power, lbl in label.items():
            final[lbl].append(len(centers.get(power, [])))

        # trajectory: year-0 baseline + each winter-adjustment snapshot
        for power, lbl in label.items():
            traj[1900][lbl].append(START_CENTERS[power])
        for e in events:
            if e["type"] == "phase_resolved" and e.get("resolved_phase", "").endswith("A"):
                year = int(e["resolved_phase"][1:5])
                cen = e.get("centers", {}) or {}
                for power, lbl in label.items():
                    traj[year][lbl].append(len(cen.get(power, [])))

        _competence(events, label, raw)

    return {"final": final, "traj": traj, "raw": raw, "n_games": len(paths)}


def _competence(events: list[dict], label: dict, raw: dict) -> None:
    """Per-power order quality, mirroring transcripts._compute_outcomes but
    scoped to a single power so it can be attributed to that power's model:
    illegal-order rate, move-support success, and self-bounces."""
    res_by_phase: dict[str, dict] = {}
    occ_post: dict[str, dict] = {}
    locs_by_phase: dict[str, set] = collections.defaultdict(set)
    move_targets: dict[str, set] = collections.defaultdict(set)

    for e in events:
        if e["type"] == "phase_resolved":
            rp = e.get("resolved_phase", "")
            res_by_phase[rp] = e.get("results", {}) or {}
            occ: dict[str, str] = {}
            for pw, units in (e.get("units", {}) or {}).items():
                for u in units:
                    t = u.split()
                    if len(t) >= 2:
                        occ[t[1].split("/")[0]] = pw
                        locs_by_phase[rp].add((t[0], t[1].split("/")[0]))
            occ_post[rp] = occ
        elif e["type"] == "orders_submitted" and e["phase"].endswith("M"):
            for o in e.get("valid", []):
                if " - " in o and " S " not in o and " C " not in o:
                    left, right = o.split(" - ", 1)
                    lt, rt = left.split(), right.split()
                    if len(lt) >= 2 and rt:
                        move_targets[e["phase"]].add(
                            (lt[0], lt[1].split("/")[0], rt[0].split("/")[0]))

    for e in events:
        if e["type"] != "orders_submitted" or not e["phase"].endswith("M"):
            continue
        lbl = label[e["power"]]
        ph = e["phase"]
        c = raw[lbl]
        valid, invalid = e.get("valid", []), e.get("invalid", [])
        c["orders"] += len(valid) + len(invalid)
        c["illegal"] += len(invalid)
        res = res_by_phase.get(ph, {})
        locs = locs_by_phase.get(ph, set())
        occ = occ_post.get(ph, {})
        for o in valid:
            if " S " in o:
                parts = o.split(" S ")
                if len(parts) == 2 and " - " in parts[1]:
                    c["supp_move"] += 1
                    unit, dest = (s.strip() for s in parts[1].split(" - ", 1))
                    failed = any(t in ("bounce", "void", "dislodged")
                                 for t in res.get(unit, ["void"]))
                    landed = bool(unit.split()) and (
                        unit.split()[0], dest.split("/")[0]) in locs
                    if not failed and landed:
                        c["supp_move_ok"] += 1
            elif " - " in o and " C " not in o:
                unit = o.split(" - ", 1)[0].strip()
                dest = o.split(" - ", 1)[1].split()[0].split("/")[0]
                if any("bounce" in t for t in res.get(unit, [])) and occ.get(dest) == e["power"]:
                    c["self_bounce"] += 1


# --- SVG primitives ---------------------------------------------------------

FONT = "-apple-system, system-ui, sans-serif"


def _svg_open(w: int, h: int, title: str) -> list[str]:
    return [
        f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
        f"font-family='{FONT}' width='{w}' height='{h}'>",
        f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
        f"font-weight='600' fill='#333'>{title}</text>",
    ]


def _legend(x: float, y: float) -> str:
    out = []
    for i, m in enumerate(ORDER):
        cx = x + i * 132
        out.append(
            f"<rect x='{cx}' y='{y-8}' width='11' height='11' rx='2' fill='{COLOR[m]}'/>"
            f"<text x='{cx+16}' y='{y+1}' font-size='11' fill='#444'>{m} "
            f"<tspan fill='#999'>{TIER[m]}</tspan></text>")
    return "".join(out)


# --- plot 1: final supply centers (the ranking) -----------------------------

def plot_final(final: dict) -> str:
    w, h = 760, 380
    pad_l, pad_b, pad_t = 56, 58, 44
    y0, y1 = 0.0, 6.0  # supply-center axis; bars start at 0
    plot_h = h - pad_b - pad_t

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    cols = [pad_l + 90 + i * 200 for i in range(len(ORDER))]
    bw = 84
    # plot 1 runs cheap -> expensive left to right: MiMo, Sonnet, Opus
    plot_order = list(reversed(ORDER))
    s = _svg_open(w, h, "1. Final supply centers by model")

    # y grid + ticks
    for v in range(int(y0), int(y1) + 1):
        yy = yf(v)
        s.append(f"<line x1='{pad_l}' y1='{yy:.1f}' x2='{w-20}' y2='{yy:.1f}' "
                 f"stroke='#eee' stroke-width='1'/>")
        s.append(f"<text x='{pad_l-8}' y='{yy+3:.1f}' text-anchor='end' "
                 f"font-size='10' fill='#999'>{v}</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>supply centers at game end</text>")

    for col, m in zip(cols, plot_order):
        vals = final[m]
        mean = statistics.mean(vals)
        # standard deviation of the mean (standard error): sample std / sqrt(n)
        sem = statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
        ym = yf(mean)
        # bar
        s.append(f"<rect x='{col-bw/2:.1f}' y='{ym:.1f}' width='{bw}' "
                 f"height='{yf(0)-ym:.1f}' rx='2' fill='{COLOR[m]}' "
                 f"fill-opacity='0.85'/>")
        # error bar: mean +/- sem, with caps
        y_hi, y_lo = yf(mean + sem), yf(mean - sem)
        s.append(f"<line x1='{col:.1f}' y1='{y_hi:.1f}' x2='{col:.1f}' "
                 f"y2='{y_lo:.1f}' stroke='#222' stroke-width='1.4'/>")
        for yy in (y_hi, y_lo):
            s.append(f"<line x1='{col-9:.1f}' y1='{yy:.1f}' x2='{col+9:.1f}' "
                     f"y2='{yy:.1f}' stroke='#222' stroke-width='1.4'/>")
        # column label
        s.append(f"<text x='{col:.0f}' y='{h-30}' text-anchor='middle' "
                 f"font-size='12' font-weight='600' fill='{COLOR[m]}'>{m}</text>")
        s.append(f"<text x='{col:.0f}' y='{h-16}' text-anchor='middle' "
                 f"font-size='9.5' fill='#999'>({len(vals)} nations)</text>")
    s.append("</svg>")
    return "\n".join(s)


# --- plot 2: supply-center trajectory ---------------------------------------

def plot_trajectory(traj: dict) -> str:
    w, h = 760, 360
    pad_l, pad_r, pad_b, pad_t = 56, 140, 50, 44
    years = sorted(traj)
    y0, y1 = 2.8, 5.4
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_b - pad_t

    def xf(yr):
        return pad_l + plot_w * (years.index(yr) / (len(years) - 1))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    def sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0

    s = _svg_open(w, h, "2. Mean supply centers by year, per model")
    # y grid at whole-and-half marks inside the range
    for v in (3.0, 3.5, 4.0, 4.5, 5.0):
        yy = yf(v)
        s.append(f"<line x1='{pad_l}' y1='{yy:.1f}' x2='{w-pad_r}' y2='{yy:.1f}' "
                 f"stroke='#eee' stroke-width='1'/>")
        s.append(f"<text x='{pad_l-8}' y='{yy+3:.1f}' text-anchor='end' "
                 f"font-size='10' fill='#999'>{v:.1f}</text>")
    # x ticks
    for yr in years:
        lbl = "start" if yr == 1900 else str(yr)
        s.append(f"<text x='{xf(yr):.1f}' y='{h-pad_b+18:.0f}' text-anchor='middle' "
                 f"font-size='10' fill='#999'>{lbl}</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>mean supply centers</text>")

    for m in ORDER:
        pts = [(xf(yr), yf(statistics.mean(traj[yr][m]))) for yr in years]
        d = " ".join(f"{'M' if i==0 else 'L'} {x:.1f} {y:.1f}"
                     for i, (x, y) in enumerate(pts))
        s.append(f"<path d='{d}' fill='none' stroke='{COLOR[m]}' stroke-width='2.5'/>")
        # markers with standard-error bars
        for yr, (x, _) in zip(years, pts):
            vals = traj[yr][m]
            mean = statistics.mean(vals)
            e = sem(vals)
            y_hi, y_lo = yf(mean + e), yf(mean - e)
            s.append(f"<line x1='{x:.1f}' y1='{y_hi:.1f}' x2='{x:.1f}' "
                     f"y2='{y_lo:.1f}' stroke='{COLOR[m]}' stroke-width='1.2'/>")
            for yy in (y_hi, y_lo):
                s.append(f"<line x1='{x-4:.1f}' y1='{yy:.1f}' x2='{x+4:.1f}' "
                         f"y2='{yy:.1f}' stroke='{COLOR[m]}' stroke-width='1.2'/>")
            s.append(f"<circle cx='{x:.1f}' cy='{yf(mean):.1f}' r='3.5' "
                     f"fill='{COLOR[m]}'/>")

    # legend at right, cheap -> frontier top to bottom: MiMo, Sonnet, Opus
    lx = w - pad_r + 20
    ly0 = pad_t + plot_h / 2 - 22
    for i, m in enumerate(["MiMo", "Sonnet", "Opus"]):
        ly = ly0 + i * 24
        s.append(f"<rect x='{lx}' y='{ly-9:.0f}' width='12' height='12' rx='2' "
                 f"fill='{COLOR[m]}'/>")
        s.append(f"<text x='{lx+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>{TIER[m]}</tspan></text>")
    s.append("</svg>")
    return "\n".join(s)


# --- plot 3: competence panels ----------------------------------------------

def plot_competence(raw: dict) -> str:
    def illegal_pct(m):
        c = raw[m]
        return 100 * c["illegal"] / c["orders"] if c["orders"] else 0

    def supp_pct(m):
        c = raw[m]
        return 100 * c["supp_move_ok"] / c["supp_move"] if c["supp_move"] else 0

    def selfb_rate(m):
        c = raw[m]
        return 100 * c["self_bounce"] / c["orders"] if c["orders"] else 0

    def supp_n(m):
        return f"n={raw[m]['supp_move']}"

    # Each panel: title, y-label, value fn, hint, per-bar sub-annotation fn
    # (None = no sub-label). The move-support panel prints its sample size on
    # every bar because the counts are small enough to mislead at a glance.
    panels = [
        ("Illegal-order rate", "% of orders", illegal_pct, "lower is better", None),
        ("Move-support success", "% of move-supports", supp_pct,
         "higher is better, but small n", supp_n),
        ("Self-bounces", "per 100 orders", selfb_rate, "lower is better", None),
    ]
    pw, ph = 250, 320
    oy = 30  # top band for the plot title
    w, h = pw * 3, ph + oy
    s = [f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
         f"font-family='{FONT}' width='{w}' height='{h}'>"]
    s.append(f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
             f"font-weight='600' fill='#333'>3. Competence by model</text>")

    for pi, (title, ylab, fn, hint, subfn) in enumerate(panels):
        ox = pi * pw
        pad_l, pad_b, pad_t = 44, 64, 50
        plot_h = ph - pad_b - pad_t
        bar_order = list(reversed(ORDER))  # MiMo, Sonnet, Opus
        vals = [fn(m) for m in bar_order]
        vmax = max(vals + [1]) * 1.25
        bw = 46
        gap = (pw - 2 * pad_l) / len(ORDER)
        s.append(f"<text x='{ox+pw/2:.0f}' y='{22+oy}' text-anchor='middle' "
                 f"font-size='12.5' font-weight='600' fill='#333'>{title}</text>")
        s.append(f"<text x='{ox+pw/2:.0f}' y='{38+oy}' text-anchor='middle' "
                 f"font-size='9.5' fill='#aaa'>{ylab} · {hint}</text>")
        baseline = oy + pad_t + plot_h
        s.append(f"<line x1='{ox+pad_l}' y1='{baseline}' x2='{ox+pw-12}' "
                 f"y2='{baseline}' stroke='#ddd' stroke-width='1'/>")
        for i, m in enumerate(bar_order):
            cx = ox + pad_l + gap * (i + 0.5)
            bh = plot_h * (vals[i] / vmax)
            by = baseline - bh
            s.append(f"<rect x='{cx-bw/2:.1f}' y='{by:.1f}' width='{bw}' "
                     f"height='{bh:.1f}' rx='2' fill='{COLOR[m]}' fill-opacity='0.85'/>")
            s.append(f"<text x='{cx:.1f}' y='{by-6:.1f}' text-anchor='middle' "
                     f"font-size='11.5' font-weight='700' fill='{COLOR[m]}'>"
                     f"{vals[i]:.1f}</text>")
            s.append(f"<text x='{cx:.1f}' y='{baseline+16:.1f}' text-anchor='middle' "
                     f"font-size='10.5' fill='#666'>{m}</text>")
            if subfn is not None:
                s.append(f"<text x='{cx:.1f}' y='{baseline+30:.1f}' "
                         f"text-anchor='middle' font-size='9' fill='#aaa'>"
                         f"{subfn(m)}</text>")
    s.append("</svg>")
    return "\n".join(s)


# --- index page -------------------------------------------------------------

def build_index(data: dict) -> str:
    raw = data["raw"]
    n = data["n_games"]
    supp_n = {m: raw[m]["supp_move"] for m in ORDER}
    css = (
        "body{font:15px/1.6 " + FONT + ";color:#222;max-width:860px;margin:0 auto;"
        "padding:32px 24px;}h1{font-size:22px;margin:0 0 4px;}"
        ".sub{color:#777;margin:0 0 24px;}figure{margin:32px 0;}"
        "figure img,figure svg{max-width:100%;height:auto;display:block;}"
        "figcaption{color:#555;font-size:13.5px;margin-top:8px;}"
        "a{color:#1b5e9b;}.back{font-size:13px;}"
    )
    body = [
        "<a class='back' href='../findings.md'>&larr; findings.md</a>",
        "<h1>Model-capability axis: the 7-game rotation</h1>",
        f"<p class='sub'>Opus (frontier) and MiMo (budget) each rotate through all "
        f"seven powers once, on opposite sides of the board, against a Sonnet field, "
        f"counterbalancing board position across {n} games to isolate model-dependant "
        f"outcomes from the nations they play.</p>",

        "<figure><object type='image/svg+xml' data='final_centers.svg'></object></figure>",

        "<figure><object type='image/svg+xml' data='sc_trajectory.svg'></object></figure>",

        "<figure><object type='image/svg+xml' data='competence.svg'></object>",
        f"<figcaption><b>Competence is where the tiers separate.</b> Illegal-order "
        f"rate ladders cleanly by price: MiMo roughly triples Opus's rate, with "
        f"Sonnet between, the same coordination-failure ladder the self-play games "
        f"show. Move-support success is noisier (only {supp_n['Opus']}/{supp_n['MiMo']} "
        f"move-supports for Opus/MiMo in 3 years, so read it as indicative). "
        f"Self-bounces echo the paradox from self-play: the budget model trips over "
        f"its own units least because it attempts the least coordination.</figcaption></figure>",

        "<p class='sub' style='margin-top:32px'>Plots derived from the seven game "
        "transcripts by <code>experiments/model_capability/build_axis_dashboard.py</code>. "
        "Per-game dashboards and the negotiation transcripts live under each game's "
        "own folder.</p>",
    ]
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Model-capability rotation</title><style>{css}</style></head>"
            f"<body>{''.join(body)}</body></html>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--games", default="scratch/model-capability-3yr",
                    help="dir holding the rotation games (each */transcript.jsonl)")
    ap.add_argument("--out", default="results/model-capability/dashboard",
                    help="output dashboard dir")
    args = ap.parse_args()

    data = extract(args.games)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_centers.svg").write_text(plot_final(data["final"]))
    (out / "sc_trajectory.svg").write_text(plot_trajectory(data["traj"]))
    (out / "competence.svg").write_text(plot_competence(data["raw"]))
    (out / "index.html").write_text(build_index(data))

    print(f"wrote dashboard to {out}/ ({data['n_games']} games)")
    for m in ORDER:
        c = data["raw"][m]
        print(f"  {m:7s} final-SC mean={statistics.mean(data['final'][m]):.2f}  "
              f"illegal={100*c['illegal']/c['orders']:.1f}%  "
              f"supp-move-ok={100*c['supp_move_ok']/max(c['supp_move'],1):.0f}% "
              f"(n={c['supp_move']})  self-bounce={c['self_bounce']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
