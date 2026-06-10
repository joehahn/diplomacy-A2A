#!/usr/bin/env python3
"""Build the LLM-capability-axis cross-game dashboard.

Reads the seven counterbalanced rotation games (Opus and MiMo each rotate
through all seven powers once, against a Sonnet field; see
experiments/llm_axis.py) and aggregates per-model rather than per-power, so
each metric is attributed to the model that drove that power. Emits three
hand-rolled inline-SVG plots plus an index.html into the output dashboard dir.
No plotting dependency, matching the per-game dashboards in transcripts.py.

    python experiments/model_capability/build_axis_dashboard.py \
        --games results/model-capability \
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
COLOR = {"Opus": "#1b5e9b", "Sonnet": "#3f8f5e", "MiMo": "#c85a23"}

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
    od_points = {m: [] for m in ORDER}                   # model->[(offence, defence)]

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
        _negotiation(events, label, raw)

        od = compute_offence_defence(events)
        for power, lbl in label.items():
            o, d = od.get(power, (0, 0))
            raw[lbl]["off_sum"] += o
            raw[lbl]["def_sum"] += d
            od_points[lbl].append((o, d))

    return {"final": final, "traj": traj, "raw": raw,
            "od_points": od_points, "n_games": len(paths)}


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
            if o.rstrip().endswith(" H"):
                c["holds"] += 1
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


_COND_RE = re.compile(r"\b(if you|if I|in exchange|in return|provided that)\b", re.I)
_ALLIANCE_RE = re.compile(
    r"\b(alliance|alliances|ally|allies|allied|coalition|coalitions|partner|"
    r"partners|partnership|pact|pacts|non-aggression|coordinate|coordinated|"
    r"coordination|cooperate|cooperation)\b|work together|together against", re.I)
_PROMISE_RE = re.compile(r"(won't|will not|stay out|no interest in|respect)", re.I)
_STOP_WORDS = {"IF", "AND", "BUT", "THE", "OUR", "ALL", "HAS", "NOT", "NEW", "HOLD",
               "SC", "YOU", "FOR", "ARE", "WAS", "WHO", "WHY", "HOW", "OUT", "OWN"}


def _negotiation(events: list[dict], label: dict, raw: dict) -> None:
    """Per-power negotiation character, mirroring transcripts._compute_outcomes:
    message volume and the shares that are conditional bargaining, alliance
    vocabulary, questions, and (heuristic) betrayals, attributed to the speaker's
    model."""
    orders_by_pp_phase: dict[str, dict[str, list[str]]] = {}
    for e in events:
        if e.get("type") == "orders_submitted":
            orders_by_pp_phase.setdefault(e["phase"], {})[e["power"]] = e.get("valid", [])
    seen_betray: set[tuple[str, str, str]] = set()
    for e in events:
        if e.get("type") != "agent_messages":
            continue
        phase, speaker = e.get("phase", ""), e.get("power", "")
        lbl = label.get(speaker)
        if lbl is None:
            continue
        c = raw[lbl]
        speaker_orders = orders_by_pp_phase.get(phase, {}).get(speaker, [])
        for _, text in (e.get("messages", {}) or {}).items():
            c["msgs"] += 1
            if _COND_RE.search(text):
                c["cond"] += 1
            if _ALLIANCE_RE.search(text):
                c["alliance"] += 1
            if "?" in text:
                c["question"] += 1
            if _PROMISE_RE.search(text):
                provs = {p for p in re.findall(r"\b([A-Z]{3})\b", text)
                         if p not in _STOP_WORDS}
                for prov in provs:
                    key = (phase, speaker, prov)
                    if key in seen_betray:
                        continue
                    for o in speaker_orders:
                        mt = re.match(r"[AF] \S+\s*-\s*(\S+)", o)
                        if mt and mt.group(1).split("/")[0] == prov:
                            c["betray"] += 1
                            seen_betray.add(key)
                            break


def compute_offence_defence(events: list[dict]) -> dict[str, tuple[int, int]]:
    """Final cumulative (offence, defence) score per power, faithfully porting
    the per-phase scoring in transcripts.render_html_viewer. Offence rewards
    taking ground (+3 dislodge a hold-supported enemy, +2 a lone enemy, +1 a
    vacant province; -1/-2 for losing a garrisoned/undefended SC). Defence scores
    units under attack (+2/+1 holding vs a supported/unsupported attack; -2/-1
    dislodged on a SC / elsewhere)."""
    results_by_phase: dict[str, dict] = {}
    owner_snaps: list[tuple[str, dict[str, str]]] = []
    occ_by_phase: dict[str, dict[str, str]] = {}
    entering_units: dict[str, dict[str, tuple[str, str]]] = {}
    sc_set: set[str] = set()
    for e in events:
        if e.get("type") != "phase_resolved":
            continue
        rp = e.get("resolved_phase", "")
        results_by_phase[rp] = e.get("results", {}) or {}
        owners: dict[str, str] = {}
        for power, provs in (e.get("centers", {}) or {}).items():
            for p in provs:
                base = p.split("/")[0]
                owners[base] = power
                sc_set.add(base)
        owner_snaps.append((rp, owners))
        occ: dict[str, str] = {}
        ent: dict[str, tuple[str, str]] = {}
        for power, units in (e.get("units", {}) or {}).items():
            for u in units:
                t = u.split()
                if len(t) >= 2:
                    base = t[1].split("/")[0]
                    occ[base] = power
                    ent[base] = (power, u)
        occ_by_phase[rp] = occ
        entering_units[e.get("next_phase", "")] = ent

    off: collections.Counter = collections.Counter()
    deff: collections.Counter = collections.Counter()

    # loss side: a supply center that changed owner costs the old owner
    for i in range(1, len(owner_snaps)):
        prev_ph, prev_ow = owner_snaps[i - 1]
        _, cur_ow = owner_snaps[i]
        prev_occ = occ_by_phase.get(prev_ph, {})
        for sc in set(prev_ow) | set(cur_ow):
            a, b = prev_ow.get(sc), cur_ow.get(sc)
            if a is None or a == b:
                continue
            off[a] += -1 if prev_occ.get(sc) == a else -2

    hold_supported: dict[str, set[str]] = {}
    for e in events:
        if e.get("type") != "orders_submitted" or not e.get("phase", "").endswith("M"):
            continue
        for o in e.get("valid", []):
            if " S " not in o:
                continue
            sup = o.split(" S ", 1)[1].strip()
            if " - " not in sup:
                hold_supported.setdefault(e["phase"], set()).add(sup)

    # gain side: every successful move at a movement phase
    for e in events:
        if e.get("type") != "orders_submitted" or not e.get("phase", "").endswith("M"):
            continue
        ph, power = e["phase"], e["power"]
        pre = entering_units.get(ph, {})
        res = results_by_phase.get(ph, {})
        for o in e.get("valid", []):
            if " - " not in o or " S " in o or " C " in o:
                continue
            unit = o.split(" - ", 1)[0].strip()
            dest = o.split(" - ", 1)[1].split()[0].split("/")[0]
            if any(t in ("bounce", "void", "dislodged") for t in res.get(unit, [])):
                continue
            tgt = pre.get(dest)
            if tgt is None:
                gain = 1
            elif tgt[0] != power:
                if any("dislodged" in t for t in res.get(tgt[1], [])):
                    gain = 3 if tgt[1] in hold_supported.get(ph, set()) else 2
                else:
                    gain = 1
            else:
                continue
            off[power] += gain

    # defence side
    moves_by_phase: dict[str, dict[str, list[str]]] = {}
    supp_by_phase: dict[str, dict[str, int]] = {}
    for e in events:
        if e.get("type") != "orders_submitted" or not e.get("phase", "").endswith("M"):
            continue
        ph, mover = e["phase"], e["power"]
        mv = moves_by_phase.setdefault(ph, {})
        sp = supp_by_phase.setdefault(ph, {})
        for o in e.get("valid", []):
            if " S " in o:
                sup = o.split(" S ", 1)[1].strip()
                if " - " in sup:
                    dest = sup.split(" - ", 1)[1].split()[0].split("/")[0]
                    sp[dest] = sp.get(dest, 0) + 1
            elif " - " in o and " C " not in o:
                dest = o.split(" - ", 1)[1].split()[0].split("/")[0]
                mv.setdefault(dest, []).append(mover)
    for ph, mv in moves_by_phase.items():
        pre = entering_units.get(ph, {})
        res = results_by_phase.get(ph, {})
        sp = supp_by_phase.get(ph, {})
        for base, (owner, unit) in pre.items():
            if not any(pw != owner for pw in mv.get(base, [])):
                continue
            if any("dislodged" in t for t in res.get(unit, [])):
                deff[owner] += -2 if base in sc_set else -1
            else:
                deff[owner] += 2 if sp.get(base, 0) > 0 else 1

    return {p: (off.get(p, 0), deff.get(p, 0)) for p in set(off) | set(deff)}


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
    # bars start at 0; the top auto-scales so longer games (leaders reaching 8-12
    # centers) do not clip, with a floor of 6 so short games keep headroom.
    def _sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
    top = max(statistics.mean(final[m]) + _sem(final[m]) for m in ORDER)
    y0, y1 = 0.0, max(6.0, float(math.ceil(top + 0.5)))
    ystep = 1 if y1 <= 8 else 2
    plot_h = h - pad_b - pad_t

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    cols = [pad_l + 90 + i * 200 for i in range(len(ORDER))]
    bw = 84
    # plot 1 runs cheap -> expensive left to right: MiMo, Sonnet, Opus
    plot_order = list(reversed(ORDER))
    s = _svg_open(w, h, "1. Final supply centers by model")

    # y grid + ticks
    for v in range(int(y0), int(y1) + 1, ystep):
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
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_b - pad_t

    def sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0

    # y-range auto-scales to the error-bar extent, padded and snapped to 0.5,
    # so a 10-year game (means spreading well past 5) does not clip.
    lo = min(statistics.mean(traj[yr][m]) - sem(traj[yr][m])
             for yr in years for m in ORDER)
    hi = max(statistics.mean(traj[yr][m]) + sem(traj[yr][m])
             for yr in years for m in ORDER)
    y0 = math.floor((lo - 0.15) * 2) / 2
    y1 = math.ceil((hi + 0.15) * 2) / 2
    ystep = 0.5 if (y1 - y0) <= 3 else 1.0

    def xf(yr):
        return pad_l + plot_w * (years.index(yr) / (len(years) - 1))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    s = _svg_open(w, h, "2. Mean supply centers by year, per model")
    # y grid
    v = y0
    while v <= y1 + 1e-9:
        yy = yf(v)
        s.append(f"<line x1='{pad_l}' y1='{yy:.1f}' x2='{w-pad_r}' y2='{yy:.1f}' "
                 f"stroke='#eee' stroke-width='1'/>")
        s.append(f"<text x='{pad_l-8}' y='{yy+3:.1f}' text-anchor='end' "
                 f"font-size='10' fill='#999'>{v:.1f}</text>")
        v += ystep
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

    # Each bar is 100 * k / n for an event count k over a (large, ~fixed)
    # denominator n, so k is approximately Poisson and the 1-sigma error on the
    # bar is 100 * sqrt(k) / n. A zero count has no Poisson error bar (sqrt 0).
    def _poisson_err(k, n):
        return 100 * math.sqrt(k) / n if n else 0.0

    def illegal_err(m):
        return _poisson_err(raw[m]["illegal"], raw[m]["orders"])

    def supp_err(m):
        return _poisson_err(raw[m]["supp_move_ok"], raw[m]["supp_move"])

    def selfb_err(m):
        return _poisson_err(raw[m]["self_bounce"], raw[m]["orders"])

    # Each panel: title, y-label, value fn, hint, per-bar sub-annotation fn
    # (None = no sub-label), 1-sigma error fn. The move-support panel prints its
    # sample size on every bar because the counts are small enough to mislead.
    panels = [
        ("Illegal-order rate", "% of orders", illegal_pct, "lower is better",
         None, illegal_err),
        ("Move-support success", "% of move-supports", supp_pct,
         "higher is better, but small n", supp_n, supp_err),
        ("Self-bounces", "per 100 orders", selfb_rate, "lower is better",
         None, selfb_err),
    ]
    pw, ph = 250, 320
    oy = 30  # top band for the plot title
    w, h = pw * 3, ph + oy
    s = [f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
         f"font-family='{FONT}' width='{w}' height='{h}'>"]
    s.append(f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
             f"font-weight='600' fill='#333'>3. Competence by model</text>")

    for pi, (title, ylab, fn, hint, subfn, efn) in enumerate(panels):
        ox = pi * pw
        pad_l, pad_b, pad_t = 44, 64, 50
        plot_h = ph - pad_b - pad_t
        bar_order = list(reversed(ORDER))  # MiMo, Sonnet, Opus
        vals = [fn(m) for m in bar_order]
        errs = [efn(m) for m in bar_order]
        # leave room for the upper error cap and the value label above it
        vmax = max([v + e for v, e in zip(vals, errs)] + [1]) * 1.15
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
            val, err = vals[i], errs[i]
            by = baseline - plot_h * (val / vmax)
            s.append(f"<rect x='{cx-bw/2:.1f}' y='{by:.1f}' width='{bw}' "
                     f"height='{baseline-by:.1f}' rx='2' fill='{COLOR[m]}' "
                     f"fill-opacity='0.85'/>")
            # 1-sigma Poisson error bar with caps
            y_hi = baseline - plot_h * ((val + err) / vmax)
            if err > 0:
                y_lo = baseline - plot_h * (max(val - err, 0.0) / vmax)
                s.append(f"<line x1='{cx:.1f}' y1='{y_hi:.1f}' x2='{cx:.1f}' "
                         f"y2='{y_lo:.1f}' stroke='#333' stroke-width='1.3'/>")
                for yy in (y_hi, y_lo):
                    s.append(f"<line x1='{cx-7:.1f}' y1='{yy:.1f}' x2='{cx+7:.1f}' "
                             f"y2='{yy:.1f}' stroke='#333' stroke-width='1.3'/>")
            s.append(f"<text x='{cx:.1f}' y='{y_hi-6:.1f}' text-anchor='middle' "
                     f"font-size='11.5' font-weight='700' fill='{COLOR[m]}'>"
                     f"{val:.1f}</text>")
            s.append(f"<text x='{cx:.1f}' y='{baseline+16:.1f}' text-anchor='middle' "
                     f"font-size='10.5' fill='#666'>{m}</text>")
            if subfn is not None:
                s.append(f"<text x='{cx:.1f}' y='{baseline+30:.1f}' "
                         f"text-anchor='middle' font-size='9' fill='#aaa'>"
                         f"{subfn(m)}</text>")
    s.append("</svg>")
    return "\n".join(s)


# --- plot 4: offence vs defence scatter -------------------------------------

def plot_scatter(od_points: dict) -> str:
    w, h = 620, 460
    pad_l, pad_r, pad_b, pad_t = 58, 150, 52, 44
    allpts = [p for m in ORDER for p in od_points[m]]
    xs = [d for _, d in allpts]
    ys = [o for o, _ in allpts]
    x0, x1 = min(xs) - 2, max(xs) + 2
    y0, y1 = min(ys) - 2, max(ys) + 2
    plot_w, plot_h = w - pad_l - pad_r, h - pad_b - pad_t

    def xf(v):
        return pad_l + plot_w * ((v - x0) / (x1 - x0))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    s = _svg_open(w, h, "4. Offence vs Defence (per nation)")
    # axis frame
    s.append(f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t+plot_h}' "
             f"stroke='#bbb' stroke-width='0.8'/>")
    s.append(f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{pad_l+plot_w}' "
             f"y2='{pad_t+plot_h}' stroke='#bbb' stroke-width='0.8'/>")
    # integer-ish ticks (step 2)
    xt = int(x0) - (int(x0) % 2)
    while xt <= x1:
        if x0 <= xt <= x1:
            s.append(f"<text x='{xf(xt):.1f}' y='{pad_t+plot_h+16:.0f}' "
                     f"text-anchor='middle' font-size='9' fill='#999'>{xt}</text>")
        xt += 2
    yt = int(y0) - (int(y0) % 2)
    while yt <= y1:
        if y0 <= yt <= y1:
            s.append(f"<text x='{pad_l-7}' y='{yf(yt)+3:.1f}' text-anchor='end' "
                     f"font-size='9' fill='#999'>{yt}</text>")
        yt += 2
    # crosshair at the field (grand) mean
    gx, gy = statistics.mean(xs), statistics.mean(ys)
    s.append(f"<line x1='{xf(gx):.1f}' y1='{pad_t}' x2='{xf(gx):.1f}' "
             f"y2='{pad_t+plot_h}' stroke='#ddd' stroke-width='1' stroke-dasharray='4 3'/>")
    s.append(f"<line x1='{pad_l}' y1='{yf(gy):.1f}' x2='{pad_l+plot_w}' "
             f"y2='{yf(gy):.1f}' stroke='#ddd' stroke-width='1' stroke-dasharray='4 3'/>")
    s.append(f"<text x='{pad_l+plot_w-2:.0f}' y='{yf(gy)-4:.1f}' text-anchor='end' "
             f"font-size='8.5' fill='#bbb'>field average</text>")
    # axis labels
    s.append(f"<text x='{pad_l+plot_w/2:.0f}' y='{h-6}' text-anchor='middle' "
             f"font-size='10' fill='#777'>Defence score per nation</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>Offence score per nation</text>")
    # faint per-nation points
    for m in ORDER:
        for o, d in od_points[m]:
            s.append(f"<circle cx='{xf(d):.1f}' cy='{yf(o):.1f}' r='3' "
                     f"fill='{COLOR[m]}' fill-opacity='0.28'/>")
    # bold model-mean markers
    for m in ORDER:
        mo = statistics.mean([o for o, _ in od_points[m]])
        md = statistics.mean([d for _, d in od_points[m]])
        s.append(f"<circle cx='{xf(md):.1f}' cy='{yf(mo):.1f}' r='7' "
                 f"fill='{COLOR[m]}' stroke='#222' stroke-width='1.4'/>")
    # legend at right: MiMo, Sonnet, Opus
    lx = w - pad_r + 22
    ly0 = pad_t + plot_h / 2 - 22
    for i, m in enumerate(["MiMo", "Sonnet", "Opus"]):
        ly = ly0 + i * 24
        s.append(f"<circle cx='{lx+5}' cy='{ly-3:.0f}' r='6' fill='{COLOR[m]}' "
                 f"stroke='#222' stroke-width='1.2'/>")
        s.append(f"<text x='{lx+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>{TIER[m]}</tspan></text>")
    s.append("</svg>")
    return "\n".join(s)


# --- per-model KPI table ----------------------------------------------------

def kpi_table(data: dict) -> str:
    raw, final = data["raw"], data["final"]
    cols = ["MiMo", "Sonnet", "Opus"]  # cheap -> frontier, matching plot 1

    def n(m):
        return len(final[m])

    def pct(num, den):
        return f"{100 * num / den:.1f}%" if den else "n/a"

    # (label, per-model value fn). Each is normalised so the three are
    # comparable despite Sonnet playing five nations per game.
    rows = [
        ("Final centers / nation", lambda m: f"{statistics.mean(final[m]):.2f}"),
        ("Offence / nation", lambda m: f"{raw[m]['off_sum']/n(m):+.1f}"),
        ("Defence / nation", lambda m: f"{raw[m]['def_sum']/n(m):+.1f}"),
        ("Messages / nation", lambda m: f"{raw[m]['msgs']/n(m):.0f}"),
        ("Conditional bargaining", lambda m: pct(raw[m]['cond'], raw[m]['msgs'])),
        ("Alliance language", lambda m: pct(raw[m]['alliance'], raw[m]['msgs'])),
        ("Betrayals", lambda m: pct(raw[m]['betray'], raw[m]['msgs'])),
        ("Hold rate", lambda m: pct(raw[m]['holds'], raw[m]['orders'])),
        ("Move-support success", lambda m: pct(raw[m]['supp_move_ok'], raw[m]['supp_move'])),
        ("Illegal orders", lambda m: pct(raw[m]['illegal'], raw[m]['orders'])),
        ("Self-bounces / 100 orders",
         lambda m: f"{100*raw[m]['self_bounce']/raw[m]['orders']:.1f}" if raw[m]['orders'] else "n/a"),
    ]
    head = "".join(
        f"<th style='color:{COLOR[m]}'>{m}<br><span style='font-weight:400;"
        f"color:#999;font-size:0.82em'>{TIER[m]}</span></th>" for m in cols)
    body = ""
    for label, fn in rows:
        cells = "".join(f"<td>{fn(m)}</td>" for m in cols)
        body += f"<tr><th class='rk'>{label}</th>{cells}</tr>"
    return (f"<table class='kpi'><tr><th class='rk'></th>{head}</tr>{body}</table>")


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
        "table.kpi{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0;}"
        "table.kpi th,table.kpi td{padding:6px 10px;text-align:right;"
        "border-bottom:1px solid #eee;}"
        "table.kpi th.rk{text-align:left;font-weight:500;color:#444;}"
        "table.kpi tr th:not(.rk){text-align:right;}"
    )
    body = [
        "<a class='back' href='https://github.com/joehahn/diplomacy-A2A/blob/main/"
        "results/model-capability/findings.md'>&larr; findings.md</a>",
        "<h1>Model-capability axis: the 7-game rotation</h1>",
        f"<p class='sub'>Opus (frontier) and MiMo (budget) each rotate through all "
        f"seven powers once, on opposite sides of the board, against Sonnet playing "
        f"the other 5 players, "
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
        f"its own units least because it attempts the least coordination. Error bars "
        f"are 1&sigma; Poisson (&radic;N on the event count, scaled by the order "
        f"total): the illegal-order ladder survives them, but they swallow the "
        f"move-support panel whole, confirming those differences are not significant "
        f"at this sample size.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='offence_defence.svg'></object>",
        "<figcaption><b>Style, the canonical dashboard's signature view.</b> Each "
        "faint dot is one nation-game (offence rewards taking ground, defence rewards "
        "surviving attack); the ringed dot is the model's mean. Opus sits low-left "
        "(least offence and defence per nation, the peace-first staff officer); MiMo "
        "sits highest on defence; Sonnet is the most offensive. The clustering near "
        "the field average is the same near-tie the supply-center plots show, now in "
        "two dimensions.</figcaption></figure>",

        "<h2 style='font-size:17px;margin:36px 0 4px'>Per-model KPIs</h2>",
        "<p class='sub' style='margin:0 0 8px'>Every metric is normalised per nation "
        "(or as a share) so the three models compare despite Sonnet playing five "
        "nations per game to Opus's and MiMo's one.</p>",
        kpi_table(data),

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
    ap.add_argument("--games", default="results/model-capability",
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
    (out / "offence_defence.svg").write_text(plot_scatter(data["od_points"]))
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
