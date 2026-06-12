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
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from diplomacy_a2a.runner import _estimate_cost  # noqa: E402  (reuse the rate table)

# --- model roster -----------------------------------------------------------

MODEL_LABEL = {
    "claude-opus-4-8": "Opus",
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5-20251001": "Haiku",
    "xiaomi/mimo-v2.5": "MiMo",
}
# Display order: frontier first; reversed() gives cheap -> frontier left to right.
ORDER = ["Opus", "Sonnet", "Haiku", "MiMo"]
TIER = {"Opus": "frontier", "Sonnet": "field", "Haiku": "small Claude",
        "MiMo": "budget"}
COLOR = {"Opus": "#1b5e9b", "Sonnet": "#3f8f5e", "Haiku": "#8a5fb0",
         "MiMo": "#c85a23"}

# Standard Diplomacy home-center counts, for the year-0 trajectory baseline.
START_CENTERS = {
    "AUSTRIA": 3, "ENGLAND": 3, "FRANCE": 3, "GERMANY": 3,
    "ITALY": 3, "RUSSIA": 4, "TURKEY": 3,
}
BOARD_AVG = 34 / 7  # all 34 supply centers / 7 powers, the no-edge baseline

# TOTAL-parameter estimates in billions: (low, central, high, label). MiMo V2.5
# is published (311B total / 15B active MoE); Anthropic discloses nothing for the
# Claude models, so Haiku/Sonnet/Opus are third-party speculation and the low-high
# spread becomes a horizontal error bar (central = geometric midpoint on the log
# axis). Active params are ~5-15% of total for the MoE models, a near-uniform log
# shift that does not change the picture, so we plot total. Treat the Claude
# figures as order-of-magnitude only.
PARAMS_B = {
    "Haiku": (15, 20, 30, "~20B (est.)"),
    "MiMo": (311, 311, 311, "311B (published)"),
    "Sonnet": (1000, 1400, 2000, "~1-2T (est.)"),
    "Opus": (1500, 2700, 5000, "~1.5-5T (est.)"),
}

# Spend rate in US dollars per minute of wall-clock, from each model's 10-year
# self-play game (game cost / elapsed time): an intrinsic burn rate independent of
# how many seats the model drives. Pinned from the committed reference games.
SPEND_PER_MIN = {
    "MiMo": 0.052, "Haiku": 0.227, "Sonnet": 0.753, "Opus": 7.509,
}


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
    final_units = {m: [] for m in ORDER}                 # final unit count per power-game
    traj = collections.defaultdict(lambda: collections.defaultdict(list))  # yr->model->[sc]
    raw = collections.defaultdict(collections.Counter)   # model->counters
    od_points = {m: [] for m in ORDER}                   # model->[(offence, defence)] finals
    tokens = collections.defaultdict(collections.Counter)  # raw_model_id -> token bucket

    for path in paths:
        events = _load(path)
        power_model = next(e for e in events if e["type"] == "run_started")["power_models"]
        label = {p: MODEL_LABEL[m] for p, m in power_model.items()}

        # final supply centers
        ended = next(e for e in events if e["type"] == "run_ended")
        for raw_m, tk in (ended.get("tokens_by_model", {}) or {}).items():
            tokens[raw_m].update(tk)
        centers = ended["final_state"]["centers"]
        units = ended["final_state"]["units"]
        for power, lbl in label.items():
            final[lbl].append(len(centers.get(power, [])))
            final_units[lbl].append(len(units.get(power, [])))

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
            path = od.get(power, [(0, 0)])
            o, d = path[-1]
            raw[lbl]["off_sum"] += o
            raw[lbl]["def_sum"] += d
            raw[lbl]["nations"] += 1  # power-games this model drove
            od_points[lbl].append((o, d))

    # per-model API cost across the rotation, and cost per nation-game driven
    cost_per_nation = {}
    for raw_m, bucket in tokens.items():
        lbl = MODEL_LABEL.get(raw_m)
        if lbl and raw[lbl]["nations"]:
            cost_per_nation[lbl] = _estimate_cost({raw_m: dict(bucket)}) / raw[lbl]["nations"]

    return {"final": final, "final_units": final_units,
            "traj": traj, "raw": raw, "od_points": od_points,
            "cost_per_nation": cost_per_nation, "n_games": len(paths)}


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
            if re.search(r"\bC\b", o) or o.rstrip().endswith(" VIA"):
                c["convoy"] += 1  # convoying fleet (C) or convoyed army (VIA)
            if o.rstrip().endswith(" VIA"):
                via_unit = o.split(" - ", 1)[0].strip()
                if any("no convoy" in t for t in res.get(via_unit, [])):
                    c["convoy_uncoord"] += 1  # convoy move with no fleet to carry it
            if " S " in o:
                c["support"] += 1
                parts = o.split(" S ")
                if len(parts) == 2 and " - " in parts[1]:
                    c["supp_move"] += 1
                    unit, dest = (s.strip() for s in parts[1].split(" - ", 1))
                    ut = unit.split()
                    if len(ut) >= 2 and (
                        ut[0], ut[1].split("/")[0],
                        dest.split("/")[0]) not in move_targets.get(ph, set()):
                        c["supp_uncoord"] += 1  # backed a move no one ordered
                    failed = any(t in ("bounce", "void", "dislodged")
                                 for t in res.get(unit, ["void"]))
                    landed = bool(unit.split()) and (
                        unit.split()[0], dest.split("/")[0]) in locs
                    if not failed and landed:
                        c["supp_move_ok"] += 1
                else:
                    c["supp_hold"] += 1
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


def compute_offence_defence(events: list[dict]) -> dict[str, list[tuple[int, int]]]:
    """Per-power cumulative (offence, defence) trajectory: a list of (off, def)
    running totals starting at (0, 0) and stepping once per resolved phase, so
    the last entry is the final score. Faithfully ports the per-phase scoring in
    transcripts.render_html_viewer. Offence rewards taking ground (+3 dislodge a
    hold-supported enemy, +2 a lone enemy, +1 a vacant province; -1/-2 for losing
    a garrisoned/undefended SC). Defence scores units under attack (+2/+1 holding
    vs a supported/unsupported attack; -2/-1 dislodged on a SC / elsewhere)."""
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

    # per-phase deltas: phase -> power -> points
    agg_delta: dict = collections.defaultdict(lambda: collections.defaultdict(int))
    def_delta: dict = collections.defaultdict(lambda: collections.defaultdict(int))

    # loss side: a supply center that changed owner costs the old owner
    for i in range(1, len(owner_snaps)):
        prev_ph, prev_ow = owner_snaps[i - 1]
        cur_ph, cur_ow = owner_snaps[i]
        prev_occ = occ_by_phase.get(prev_ph, {})
        for sc in set(prev_ow) | set(cur_ow):
            a, b = prev_ow.get(sc), cur_ow.get(sc)
            if a is None or a == b:
                continue
            agg_delta[cur_ph][a] += -1 if prev_occ.get(sc) == a else -2

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
            agg_delta[ph][power] += gain

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
                def_delta[ph][owner] += -2 if base in sc_set else -1
            else:
                def_delta[ph][owner] += 2 if sp.get(base, 0) > 0 else 1

    # accumulate into a (off, def) trajectory per power, one step per phase
    phase_seq = [p for p, _ in owner_snaps]
    powers = sorted({pw for _, ow in owner_snaps for pw in ow.values()})
    traj: dict[str, list[tuple[int, int]]] = {p: [(0, 0)] for p in powers}
    ro: dict[str, int] = {p: 0 for p in powers}
    rd: dict[str, int] = {p: 0 for p in powers}
    for ph in phase_seq:
        for p, dv in agg_delta.get(ph, {}).items():
            ro[p] = ro.get(p, 0) + dv
        for p, dv in def_delta.get(ph, {}).items():
            rd[p] = rd.get(p, 0) + dv
        for p in powers:
            traj[p].append((ro.get(p, 0), rd.get(p, 0)))
    return traj


# --- SVG primitives ---------------------------------------------------------

FONT = "-apple-system, system-ui, sans-serif"


def _svg_open(w: int, h: int, title: str) -> list[str]:
    return [
        f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
        f"font-family='{FONT}' width='{w}' height='{h}'>",
        f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
        f"font-weight='600' fill='#333'>{title}</text>",
    ]


def _fit_legend(s: list, lx: float, y: float, xlabel: str, b: float, r2: float):
    """Append a power-law fit entry to a right-side legend: a dashed swatch, then
    the formula SC proportional to xlabel^b, with R^2 on the next line."""
    s.append(f"<line x1='{lx}' y1='{y}' x2='{lx+20}' y2='{y}' stroke='#888' "
             f"stroke-width='1.6' stroke-dasharray='5 3'/>")
    s.append(f"<text x='{lx+26}' y='{y+4}' font-size='10' fill='#555'>"
             f"SC &#8733; {xlabel}<tspan baseline-shift='super' font-size='7'>"
             f"{b:.2f}</tspan></text>")
    s.append(f"<text x='{lx+26}' y='{y+19}' font-size='10' fill='#777'>"
             f"R&#178; = {r2:.2f}</text>")


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

    # evenly space one bar per model across the plot width
    slot = (w - pad_l - 20) / len(ORDER)
    cols = [pad_l + slot * (i + 0.5) for i in range(len(ORDER))]
    bw = min(84, slot * 0.5)
    # plot 1 runs cheap -> expensive left to right: MiMo, Haiku, Sonnet, Opus
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
    legend_models = list(reversed(ORDER))
    ly0 = pad_t + plot_h / 2 - (len(legend_models) - 1) * 12
    for i, m in enumerate(legend_models):
        ly = ly0 + i * 24
        s.append(f"<rect x='{lx}' y='{ly-9:.0f}' width='12' height='12' rx='2' "
                 f"fill='{COLOR[m]}'/>")
        s.append(f"<text x='{lx+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>{TIER[m]}</tspan></text>")
    s.append("</svg>")
    return "\n".join(s)


# --- plot 3: dominant / squeezed fraction over time -------------------------

def plot_threshold_trajectories(traj: dict) -> str:
    """Two adjacent time series: the fraction of each model's games in which its
    nation is dominant (SC >= 6, left) or squeezed (SC <= 3, right), by year,
    with binomial standard-error bars."""
    years = sorted(traj)
    w, h = 760, 380
    pad_t, pad_b = 60, 78
    plot_h = h - pad_t - pad_b
    half = w / 2
    pad_l, pad_r = 48, 24
    plot_w = half - pad_l - pad_r

    def xf(ox, yr):
        return ox + pad_l + plot_w * (years.index(yr) / (len(years) - 1))

    def yf(v):
        return pad_t + plot_h * (1 - v)            # v is a fraction in [0, 1]

    s = _svg_open(w, h, "3. Dominant and squeezed games over time")
    s.append(f"<text x='14' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 14 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>fraction of this model's games</text>")

    panels = [(0.0, "Dominant (SC ≥ 6)", lambda v: v >= 6),
              (half, "Squeezed (SC ≤ 3)", lambda v: v <= 3)]
    for ox, ptitle, ok in panels:
        s.append(f"<text x='{ox+pad_l+plot_w/2:.0f}' y='{pad_t-16}' "
                 f"text-anchor='middle' font-size='12' font-weight='600' "
                 f"fill='#333'>{ptitle}</text>")
        for gy in (0.0, 0.25, 0.5, 0.75, 1.0):
            yy = yf(gy)
            s.append(f"<line x1='{ox+pad_l}' y1='{yy:.1f}' x2='{ox+pad_l+plot_w}' "
                     f"y2='{yy:.1f}' stroke='#eee' stroke-width='1'/>")
            s.append(f"<text x='{ox+pad_l-7}' y='{yy+3:.1f}' text-anchor='end' "
                     f"font-size='9' fill='#999'>{gy:.2f}</text>")
        for yr in years:
            if yr % 2 == 0:
                lbl = "start" if yr == 1900 else str(yr)
                s.append(f"<text x='{xf(ox, yr):.1f}' y='{pad_t+plot_h+16:.0f}' "
                         f"text-anchor='middle' font-size='9' fill='#999'>{lbl}</text>")
        for m in ORDER:
            pts = []
            for yr in years:
                vals = traj[yr][m]
                n = len(vals)
                p = sum(1 for v in vals if ok(v)) / n if n else 0.0
                e = math.sqrt(p * (1 - p) / n) if n else 0.0
                pts.append((xf(ox, yr), p, e))
            d = " ".join(f"{'M' if i == 0 else 'L'} {x:.1f} {yf(p):.1f}"
                         for i, (x, p, _) in enumerate(pts))
            s.append(f"<path d='{d}' fill='none' stroke='{COLOR[m]}' stroke-width='2.2'/>")
            for x, p, e in pts:
                if e > 0:
                    y_hi, y_lo = yf(min(p + e, 1.0)), yf(max(p - e, 0.0))
                    s.append(f"<line x1='{x:.1f}' y1='{y_hi:.1f}' x2='{x:.1f}' "
                             f"y2='{y_lo:.1f}' stroke='{COLOR[m]}' stroke-width='1.1'/>")
                    for yy in (y_hi, y_lo):
                        s.append(f"<line x1='{x-3:.1f}' y1='{yy:.1f}' x2='{x+3:.1f}' "
                                 f"y2='{yy:.1f}' stroke='{COLOR[m]}' stroke-width='1.1'/>")
                s.append(f"<circle cx='{x:.1f}' cy='{yf(p):.1f}' r='3' fill='{COLOR[m]}'/>")

    items = list(reversed(ORDER))                  # MiMo, Haiku, Sonnet, Opus
    cur = w / 2 - len(items) * 60
    for m in items:
        s.append(f"<rect x='{cur:.0f}' y='{h-20}' width='12' height='12' rx='2' "
                 f"fill='{COLOR[m]}'/>")
        s.append(f"<text x='{cur+17:.0f}' y='{h-10}' font-size='11' fill='#444'>{m}</text>")
        cur += 120
    s.append("</svg>")
    return "\n".join(s)


# --- plots 4 & 5: competence and negotiation bar panels ---------------------

def _poisson_err(k: int, n: int, scale: float = 100.0) -> tuple[float, bool]:
    """1-sigma Poisson error on a bar of value scale*k/n. k is an event count
    over a large, ~fixed denominator n, so sigma_k = sqrt(k). A zero count is a
    one-sided upper limit: observing 0 implies under one event, so sigma < 1.
    Returns (magnitude, is_upper_limit)."""
    if not n:
        return (0.0, False)
    if k == 0:
        return (scale * 1.0 / n, True)
    return (scale * math.sqrt(k) / n, False)


def _rate(raw, m, num, den, scale=100.0):
    """(value, poisson_error) for scale * raw[m][num] / raw[m][den]."""
    c = raw[m]
    v = scale * c[num] / c[den] if c[den] else 0.0
    return v, _poisson_err(c[num], c[den], scale)


def _bar_panels(number: int, title: str, panels: list,
                per_row: int = None, show_values: bool = False) -> str:
    """Render a grid of bar charts with Poisson error bars, MiMo -> Sonnet ->
    Opus, wrapping at per_row panels. Each panel is
    (panel_title, hint, {m: (value, (err, is_limit))}, [fmt]); fmt is the value
    label format, used only when show_values is set."""
    pw, ph, oy = 250, 320, 30
    per_row = per_row or len(panels)
    nrows = -(-len(panels) // per_row)
    w, h = pw * per_row, oy + nrows * ph
    pad_l, pad_b, pad_t = 44, 64, 50
    plot_h = ph - pad_b - pad_t
    gap = (pw - 2 * pad_l) / len(ORDER)
    bw = min(46, gap * 0.78)  # scales down so 4 bars per panel still fit
    bar_order = list(reversed(ORDER))  # MiMo, Haiku, Sonnet, Opus
    s = [f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
         f"font-family='{FONT}' width='{w}' height='{h}'>",
         f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
         f"font-weight='600' fill='#333'>{number}. {title}</text>"]
    for pi, panel in enumerate(panels):
        ptitle, hint, data = panel[0], panel[1], panel[2]
        fmt = panel[3] if len(panel) > 3 else "{:.1f}"
        ox = (pi % per_row) * pw
        top = oy + (pi // per_row) * ph
        vals = [data[m][0] for m in bar_order]
        errs = [data[m][1] for m in bar_order]
        vmax = max([v + e[0] for v, e in zip(vals, errs)] + [1e-6]) * (
            1.2 if show_values else 1.12)
        s.append(f"<text x='{ox+pw/2:.0f}' y='{22+top}' text-anchor='middle' "
                 f"font-size='12.5' font-weight='600' fill='#333'>{ptitle}</text>")
        s.append(f"<text x='{ox+pw/2:.0f}' y='{38+top}' text-anchor='middle' "
                 f"font-size='9.5' fill='#aaa'>{hint}</text>")
        baseline = top + pad_t + plot_h
        s.append(f"<line x1='{ox+pad_l}' y1='{baseline}' x2='{ox+pw-12}' "
                 f"y2='{baseline}' stroke='#ddd' stroke-width='1'/>")
        for i, m in enumerate(bar_order):
            cx = ox + pad_l + gap * (i + 0.5)
            val, (err, is_limit) = vals[i], errs[i]
            by = baseline - plot_h * (val / vmax)
            s.append(f"<rect x='{cx-bw/2:.1f}' y='{by:.1f}' width='{bw}' "
                     f"height='{baseline-by:.1f}' rx='2' fill='{COLOR[m]}' "
                     f"fill-opacity='0.85'/>")
            # symmetric 1-sigma bar, or one-sided upper limit for a zero count
            y_hi = baseline - plot_h * ((val + err) / vmax)
            if err > 0:
                y_lo = by if is_limit else baseline - plot_h * (max(val - err, 0.0) / vmax)
                s.append(f"<line x1='{cx:.1f}' y1='{y_hi:.1f}' x2='{cx:.1f}' "
                         f"y2='{y_lo:.1f}' stroke='#333' stroke-width='1.3'/>")
                for yy in ((y_hi,) if is_limit else (y_hi, y_lo)):
                    s.append(f"<line x1='{cx-7:.1f}' y1='{yy:.1f}' x2='{cx+7:.1f}' "
                             f"y2='{yy:.1f}' stroke='#333' stroke-width='1.3'/>")
            if show_values:
                s.append(f"<text x='{cx:.1f}' y='{y_hi-6:.1f}' text-anchor='middle' "
                         f"font-size='11.5' font-weight='700' fill='{COLOR[m]}'>"
                         f"{fmt.format(val)}</text>")
            s.append(f"<text x='{cx:.1f}' y='{baseline+16:.1f}' text-anchor='middle' "
                     f"font-size='10.5' fill='#666'>{m}</text>")
    s.append("</svg>")
    return "\n".join(s)


def plot_competence(raw: dict) -> str:
    panels = [
        # row 1: error / coordination-failure metrics
        ("Illegal-order rate", "% of orders · lower is better",
         {m: _rate(raw, m, "illegal", "orders") for m in ORDER}, "{:.1f}%"),
        ("Self-bounces", "per 100 orders · lower is better",
         {m: _rate(raw, m, "self_bounce", "orders") for m in ORDER}, "{:.1f}"),
        ("Uncoordinated supports", "% of move-supports · lower is better",
         {m: _rate(raw, m, "supp_uncoord", "supp_move") for m in ORDER}, "{:.1f}%"),
        ("Uncoordinated convoys", "% of orders · rare",
         {m: _rate(raw, m, "convoy_uncoord", "orders") for m in ORDER}, "{:.1f}%"),
        # row 2: order-mix and coordination metrics
        ("Hold rate", "% of orders · passivity",
         {m: _rate(raw, m, "holds", "orders") for m in ORDER}, "{:.1f}%"),
        ("Support rate", "% of orders · coordination effort",
         {m: _rate(raw, m, "support", "orders") for m in ORDER}, "{:.1f}%"),
        ("Move-support success", "% of move-supports · higher is better",
         {m: _rate(raw, m, "supp_move_ok", "supp_move") for m in ORDER}, "{:.1f}%"),
        ("Convoy rate", "% of orders · rare",
         {m: _rate(raw, m, "convoy", "orders") for m in ORDER}, "{:.1f}%"),
    ]
    return _bar_panels(4, "Competence by model", panels, per_row=4, show_values=True)


def plot_negotiation(raw: dict) -> str:
    panels = [
        ("Messages / nation", "count per nation-game",
         {m: _rate(raw, m, "msgs", "nations", scale=1.0) for m in ORDER}, "{:.0f}"),
        ("Conditional bargaining", "% of messages",
         {m: _rate(raw, m, "cond", "msgs") for m in ORDER}, "{:.1f}%"),
        ("Alliance language", "% of messages",
         {m: _rate(raw, m, "alliance", "msgs") for m in ORDER}, "{:.1f}%"),
        ("Betrayals", "% of messages · heuristic",
         {m: _rate(raw, m, "betray", "msgs") for m in ORDER}, "{:.1f}%"),
    ]
    return _bar_panels(5, "Negotiation by model", panels, show_values=True)


def plot_od_means(od_points: dict) -> str:
    """Mean final offence (y) vs defence (x) per model, one point each, with
    horizontal and vertical 1-sigma standard-error whiskers across the model's
    nation-games."""
    def stat(vals):
        mean = statistics.mean(vals)
        sem = statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
        return mean, sem

    st = {}  # model -> (mean_o, sem_o, mean_d, sem_d)
    for m in ORDER:
        mo, so = stat([o for o, _ in od_points[m]])
        md, sd = stat([d for _, d in od_points[m]])
        st[m] = (mo, so, md, sd)

    w, h = 560, 440
    pad_l, pad_r, pad_b, pad_t = 58, 150, 52, 44
    x0 = min(st[m][2] - st[m][3] for m in ORDER) - 0.6
    x1 = max(st[m][2] + st[m][3] for m in ORDER) + 0.6
    y0 = min(st[m][0] - st[m][1] for m in ORDER) - 0.6
    y1 = max(st[m][0] + st[m][1] for m in ORDER) + 0.6
    plot_w, plot_h = w - pad_l - pad_r, h - pad_b - pad_t

    def xf(v):
        return pad_l + plot_w * ((v - x0) / (x1 - x0))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    s = _svg_open(w, h, "6. Mean offence vs defence per model")
    s.append(f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t+plot_h}' "
             f"stroke='#bbb' stroke-width='0.8'/>")
    s.append(f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{pad_l+plot_w}' "
             f"y2='{pad_t+plot_h}' stroke='#bbb' stroke-width='0.8'/>")
    for v in range(math.ceil(x0), int(x1) + 1):
        s.append(f"<text x='{xf(v):.1f}' y='{pad_t+plot_h+16:.0f}' text-anchor='middle' "
                 f"font-size='9' fill='#999'>{v}</text>")
    for v in range(math.ceil(y0), int(y1) + 1):
        s.append(f"<text x='{pad_l-7}' y='{yf(v)+3:.1f}' text-anchor='end' "
                 f"font-size='9' fill='#999'>{v}</text>")
    s.append(f"<text x='{pad_l+plot_w/2:.0f}' y='{h-6}' text-anchor='middle' "
             f"font-size='10' fill='#777'>Defence score per nation</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>Offence score per nation</text>")
    for m in ORDER:
        mo, so, md, sd = st[m]
        cx, cy = xf(md), yf(mo)
        col = COLOR[m]
        # horizontal whisker (defence)
        s.append(f"<line x1='{xf(md-sd):.1f}' y1='{cy:.1f}' x2='{xf(md+sd):.1f}' "
                 f"y2='{cy:.1f}' stroke='{col}' stroke-width='1.6'/>")
        for xx in (xf(md - sd), xf(md + sd)):
            s.append(f"<line x1='{xx:.1f}' y1='{cy-5:.1f}' x2='{xx:.1f}' "
                     f"y2='{cy+5:.1f}' stroke='{col}' stroke-width='1.6'/>")
        # vertical whisker (offence)
        s.append(f"<line x1='{cx:.1f}' y1='{yf(mo-so):.1f}' x2='{cx:.1f}' "
                 f"y2='{yf(mo+so):.1f}' stroke='{col}' stroke-width='1.6'/>")
        for yy in (yf(mo - so), yf(mo + so)):
            s.append(f"<line x1='{cx-5:.1f}' y1='{yy:.1f}' x2='{cx+5:.1f}' "
                     f"y2='{yy:.1f}' stroke='{col}' stroke-width='1.6'/>")
        s.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='6' fill='{col}' "
                 f"stroke='#222' stroke-width='1.4'/>")
    # legend at right
    lx = w - pad_r + 22
    legend_models = list(reversed(ORDER))
    ly0 = pad_t + plot_h / 2 - (len(legend_models) - 1) * 12
    for i, m in enumerate(legend_models):
        ly = ly0 + i * 24
        s.append(f"<circle cx='{lx+5}' cy='{ly-3:.0f}' r='6' fill='{COLOR[m]}' "
                 f"stroke='#222' stroke-width='1.2'/>")
        s.append(f"<text x='{lx+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>{TIER[m]}</tspan></text>")
    s.append("</svg>")
    return "\n".join(s)



# --- plot 7: cost-performance frontier (prototype) --------------------------

def plot_cost_frontier(data: dict) -> str:
    """Per-dollar view: each KPI plotted against cost per nation-game (log x),
    one point per model. A near-flat frontier means paying more buys no gain on
    that KPI; a sloped one means it does. Prototype: at 3 years the models are
    near-tied, so this mostly shows MiMo's cost dominance until 10-year games
    let territory separate."""
    raw, final, cost = data["raw"], data["final"], data["cost_per_nation"]

    def sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0

    def rate(m, num, den):
        c = raw[m]
        v = 100 * c[num] / c[den] if c[den] else 0.0
        return v, _poisson_err(c[num], c[den])[0]

    def mistakes(m):
        # disjoint error events (invalid orders, self-bounces, supports backing a
        # move no one made), as a share of all orders
        c = raw[m]
        k = c["illegal"] + c["self_bounce"] + c["supp_uncoord"]
        v = 100 * k / c["orders"] if c["orders"] else 0.0
        return v, _poisson_err(k, c["orders"])[0]

    panels = [
        ("Final centers / nation", "outcome · higher is better",
         {m: (statistics.mean(final[m]), sem(final[m])) for m in ORDER}, "{:.2f}"),
        ("Total mistakes", "illegal + self-bounce + uncoord · lower is better",
         {m: mistakes(m) for m in ORDER}, "{:.1f}%"),
        ("Illegal-order rate", "% of orders · lower is better",
         {m: rate(m, "illegal", "orders") for m in ORDER}, "{:.1f}%"),
    ]
    pw, ph, oy, per_row = 250, 340, 30, 3
    nrows = -(-len(panels) // per_row)
    w, h = pw * per_row, oy + nrows * ph + 22
    pad_l, pad_b, pad_t = 50, 64, 52
    plot_h = ph - pad_b - pad_t
    plot_w = pw - pad_l - 20
    lx = {m: math.log10(cost[m]) for m in ORDER}
    x0 = min(lx.values()) - 0.55
    x1 = max(lx.values()) + 0.55
    cost_order = sorted(ORDER, key=lambda m: cost[m])  # cheap -> frontier

    def xf(ox, v):
        return ox + pad_l + plot_w * ((v - x0) / (x1 - x0))

    s = [f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
         f"font-family='{FONT}' width='{w}' height='{h}'>",
         f"<text x='{w/2:.0f}' y='20' text-anchor='middle' font-size='13' "
         f"font-weight='600' fill='#333'>7. KPIs per dollar "
         f"(cost-performance frontier)</text>"]
    for pi, (ptitle, hint, dat, fmt) in enumerate(panels):
        ox = (pi % per_row) * pw
        top = oy + (pi // per_row) * ph
        ys = [dat[m][0] for m in ORDER]
        es = [dat[m][1] for m in ORDER]
        y0 = min(y - e for y, e in zip(ys, es))
        y1 = max(y + e for y, e in zip(ys, es))
        pad = (y1 - y0) * 0.3 + 1e-6
        y0, y1 = y0 - pad, y1 + pad

        def yf(v, top=top, y0=y0, y1=y1):
            return top + pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

        base = top + pad_t + plot_h
        s.append(f"<text x='{ox+pw/2:.0f}' y='{22+top}' text-anchor='middle' "
                 f"font-size='12.5' font-weight='600' fill='#333'>{ptitle}</text>")
        s.append(f"<text x='{ox+pw/2:.0f}' y='{38+top}' text-anchor='middle' "
                 f"font-size='9.5' fill='#aaa'>{hint}</text>")
        s.append(f"<line x1='{ox+pad_l}' y1='{base}' x2='{ox+pad_l+plot_w}' "
                 f"y2='{base}' stroke='#bbb' stroke-width='0.8'/>")
        for lv, lbl in ((-2, "$0.01"), (-1, "$0.10"), (0, "$1"), (1, "$10")):
            if x0 <= lv <= x1:
                s.append(f"<line x1='{xf(ox,lv):.1f}' y1='{base}' "
                         f"x2='{xf(ox,lv):.1f}' y2='{base+3}' stroke='#bbb'/>")
                s.append(f"<text x='{xf(ox,lv):.1f}' y='{base+15:.0f}' "
                         f"text-anchor='middle' font-size='9' fill='#999'>{lbl}</text>")
        s.append(f"<text x='{ox+pad_l+plot_w/2:.0f}' y='{base+32:.0f}' "
                 f"text-anchor='middle' font-size='9.5' fill='#888'>"
                 f"cost / nation-game</text>")
        # faint frontier line through points in ascending-cost order
        line = " ".join(
            f"{'M' if i == 0 else 'L'} {xf(ox,lx[m]):.1f} {yf(dat[m][0]):.1f}"
            for i, m in enumerate(cost_order))
        s.append(f"<path d='{line}' fill='none' stroke='#ccc' stroke-width='1.5'/>")
        for m in ORDER:
            cx, cy, e = xf(ox, lx[m]), yf(dat[m][0]), dat[m][1]
            if e > 0:
                s.append(f"<line x1='{cx:.1f}' y1='{yf(dat[m][0]-e):.1f}' "
                         f"x2='{cx:.1f}' y2='{yf(dat[m][0]+e):.1f}' "
                         f"stroke='{COLOR[m]}' stroke-width='1.4'/>")
                for yy in (yf(dat[m][0] - e), yf(dat[m][0] + e)):
                    s.append(f"<line x1='{cx-4:.1f}' y1='{yy:.1f}' x2='{cx+4:.1f}' "
                             f"y2='{yy:.1f}' stroke='{COLOR[m]}' stroke-width='1.4'/>")
            s.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='5' fill='{COLOR[m]}' "
                     f"stroke='#222' stroke-width='1.2'/>")
            s.append(f"<text x='{cx:.1f}' y='{yf(dat[m][0]+e)-7:.1f}' "
                     f"text-anchor='middle' font-size='10.5' font-weight='700' "
                     f"fill='{COLOR[m]}'>{fmt.format(dat[m][0])}</text>")
    # shared legend, centered at the bottom
    items = [(m, f"{m} (${cost[m]:.2f})") for m in cost_order]
    total_w = sum(9 + 7 + len(lbl) * 6.0 + 22 for _, lbl in items)
    cur = w / 2 - total_w / 2
    for m, lbl in items:
        s.append(f"<rect x='{cur:.1f}' y='{h-13}' width='11' height='11' rx='2' "
                 f"fill='{COLOR[m]}'/>")
        s.append(f"<text x='{cur+16:.1f}' y='{h-4}' font-size='10.5' fill='#555'>"
                 f"{lbl}</text>")
        cur += 9 + 7 + len(lbl) * 6.0 + 22
    s.append("</svg>")
    return "\n".join(s)


# --- plot 8: final centers vs model size (speculative) ----------------------

def plot_param_frontier(data: dict) -> str:
    """Final supply centers vs total parameter count (log x). Vertical bars are
    1-sigma standard error on centers; horizontal bars are the wide third-party
    speculation range on size (Sonnet and Opus are undisclosed, so the bar spans
    the published guesses). Tests whether raw scale predicts territory."""
    final = data["final"]

    def sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0

    w, h = 620, 440
    pad_l, pad_r, pad_b, pad_t = 56, 160, 56, 44
    lx = {m: math.log10(PARAMS_B[m][1]) for m in ORDER}
    lo = {m: math.log10(PARAMS_B[m][0]) for m in ORDER}
    hi = {m: math.log10(PARAMS_B[m][2]) for m in ORDER}
    yv = {m: statistics.mean(final[m]) for m in ORDER}
    ye = {m: sem(final[m]) for m in ORDER}
    x0 = min(lo.values()) - 0.6
    x1 = max(hi.values()) + 0.4
    y0 = min(yv[m] - ye[m] for m in ORDER) - 0.5
    y1 = max(yv[m] + ye[m] for m in ORDER) + 0.5
    plot_w, plot_h = w - pad_l - pad_r, h - pad_b - pad_t

    def xf(v):
        return pad_l + plot_w * ((v - x0) / (x1 - x0))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    s = _svg_open(w, h, "8. Final supply centers vs model size")
    s.append(f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t+plot_h}' "
             f"stroke='#bbb' stroke-width='0.8'/>")
    s.append(f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{pad_l+plot_w}' "
             f"y2='{pad_t+plot_h}' stroke='#bbb' stroke-width='0.8'/>")
    for lv, lbl in ((0, "1B"), (1, "10B"), (2, "100B"), (3, "1T"), (4, "10T")):
        if x0 <= lv <= x1:
            s.append(f"<line x1='{xf(lv):.1f}' y1='{pad_t+plot_h}' x2='{xf(lv):.1f}' "
                     f"y2='{pad_t+plot_h+3}' stroke='#bbb'/>")
            s.append(f"<text x='{xf(lv):.1f}' y='{pad_t+plot_h+16:.0f}' "
                     f"text-anchor='middle' font-size='9' fill='#999'>{lbl}</text>")
    for v in range(math.ceil(y0), int(y1) + 1):
        s.append(f"<text x='{pad_l-7}' y='{yf(v)+3:.1f}' text-anchor='end' "
                 f"font-size='9' fill='#999'>{v}</text>")
    s.append(f"<text x='{pad_l+plot_w/2:.0f}' y='{h-6}' text-anchor='middle' "
             f"font-size='10' fill='#777'>total parameters (log, speculative)</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>supply centers / nation</text>")

    # best-fit power law SC = a * params^b (least squares in log10-log10 space),
    # drawn as a dashed curve extended across 10B -> 10T
    fx = [lx[m] for m in ORDER]
    fy = [math.log10(yv[m]) for m in ORDER]
    nfit = len(ORDER)
    mfx, mfy = sum(fx) / nfit, sum(fy) / nfit
    b_exp = (sum((x - mfx) * (y - mfy) for x, y in zip(fx, fy))
             / sum((x - mfx) ** 2 for x in fx))
    a_int = mfy - b_exp * mfx
    ss_tot = sum((y - mfy) ** 2 for y in fy)
    ss_res = sum((y - (a_int + b_exp * x)) ** 2 for x, y in zip(fx, fy))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    cx0, cx1 = math.log10(10), math.log10(10_000)  # 10B -> 10T
    fit_pts = " ".join(
        f"{xf(u):.1f},{yf(10 ** (a_int + b_exp * u)):.1f}"
        for u in (cx0 + (cx1 - cx0) * i / 24 for i in range(25)))
    s.append(f"<polyline points='{fit_pts}' fill='none' stroke='#888' "
             f"stroke-width='1.6' stroke-dasharray='6 4'/>")

    for m in ORDER:
        cx, cy, col = xf(lx[m]), yf(yv[m]), COLOR[m]
        # horizontal parameter-uncertainty bar
        if hi[m] > lo[m]:
            s.append(f"<line x1='{xf(lo[m]):.1f}' y1='{cy:.1f}' x2='{xf(hi[m]):.1f}' "
                     f"y2='{cy:.1f}' stroke='{col}' stroke-width='1.6'/>")
            for xx in (xf(lo[m]), xf(hi[m])):
                s.append(f"<line x1='{xx:.1f}' y1='{cy-5:.1f}' x2='{xx:.1f}' "
                         f"y2='{cy+5:.1f}' stroke='{col}' stroke-width='1.6'/>")
        # vertical standard-error bar on centers
        if ye[m] > 0:
            s.append(f"<line x1='{cx:.1f}' y1='{yf(yv[m]-ye[m]):.1f}' x2='{cx:.1f}' "
                     f"y2='{yf(yv[m]+ye[m]):.1f}' stroke='{col}' stroke-width='1.6'/>")
            for yy in (yf(yv[m] - ye[m]), yf(yv[m] + ye[m])):
                s.append(f"<line x1='{cx-5:.1f}' y1='{yy:.1f}' x2='{cx+5:.1f}' "
                         f"y2='{yy:.1f}' stroke='{col}' stroke-width='1.6'/>")
        s.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='6' fill='{col}' "
                 f"stroke='#222' stroke-width='1.4'/>")
    # legend at right with the size estimates and the fit
    lxleg = w - pad_r + 18
    legend_models = list(reversed(ORDER))
    ly0 = pad_t + plot_h / 2 - (len(legend_models) - 1) * 13 - 22
    for i, m in enumerate(legend_models):
        ly = ly0 + i * 26
        s.append(f"<circle cx='{lxleg+5}' cy='{ly-3:.0f}' r='6' fill='{COLOR[m]}' "
                 f"stroke='#222' stroke-width='1.2'/>")
        s.append(f"<text x='{lxleg+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>{PARAMS_B[m][3]}</tspan></text>")
    _fit_legend(s, lxleg, ly0 + len(legend_models) * 26 + 6, "params", b_exp, r2)
    s.append("</svg>")
    return "\n".join(s)


# --- plot 9: SC vs spend rate ------------------------------------------------

def plot_spend_frontier(final: dict) -> str:
    """Final supply centers against each model's spend rate (US dollars per minute
    of wall-clock in its self-play game), on a log x-axis, with a best-fit power
    law. Burn rate is an intrinsic model property, like size in plot 8."""
    def sem(vals):
        return statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0

    w, h = 620, 440
    pad_l, pad_r, pad_b, pad_t = 56, 160, 56, 44
    lx = {m: math.log10(SPEND_PER_MIN[m]) for m in ORDER}
    yv = {m: statistics.mean(final[m]) for m in ORDER}
    ye = {m: sem(final[m]) for m in ORDER}
    x0 = min(lx.values()) - 0.4
    x1 = max(lx.values()) + 0.4
    y0 = min(yv[m] - ye[m] for m in ORDER) - 0.5
    y1 = max(yv[m] + ye[m] for m in ORDER) + 0.5
    plot_w, plot_h = w - pad_l - pad_r, h - pad_b - pad_t

    def xf(v):
        return pad_l + plot_w * ((v - x0) / (x1 - x0))

    def yf(v):
        return pad_t + plot_h * (1 - (v - y0) / (y1 - y0))

    s = _svg_open(w, h, "9. Final supply centers vs spend rate")
    s.append(f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t+plot_h}' "
             f"stroke='#bbb' stroke-width='0.8'/>")
    s.append(f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{pad_l+plot_w}' "
             f"y2='{pad_t+plot_h}' stroke='#bbb' stroke-width='0.8'/>")
    for lv, lbl in ((-2, "$0.01"), (-1, "$0.10"), (0, "$1"), (1, "$10"), (2, "$100")):
        if x0 <= lv <= x1:
            s.append(f"<line x1='{xf(lv):.1f}' y1='{pad_t+plot_h}' x2='{xf(lv):.1f}' "
                     f"y2='{pad_t+plot_h+3}' stroke='#bbb'/>")
            s.append(f"<text x='{xf(lv):.1f}' y='{pad_t+plot_h+16:.0f}' "
                     f"text-anchor='middle' font-size='9' fill='#999'>{lbl}</text>")
    for v in range(math.ceil(y0), int(y1) + 1):
        s.append(f"<text x='{pad_l-7}' y='{yf(v)+3:.1f}' text-anchor='end' "
                 f"font-size='9' fill='#999'>{v}</text>")
    s.append(f"<text x='{pad_l+plot_w/2:.0f}' y='{h-6}' text-anchor='middle' "
             f"font-size='10' fill='#777'>spend rate (dollars / minute, log)</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>supply centers / nation</text>")

    # best-fit power law SC = a * ($/min)^b (least squares in log10-log10 space)
    fx = [lx[m] for m in ORDER]
    fy = [math.log10(yv[m]) for m in ORDER]
    nfit = len(ORDER)
    mfx, mfy = sum(fx) / nfit, sum(fy) / nfit
    b_exp = (sum((x - mfx) * (y - mfy) for x, y in zip(fx, fy))
             / sum((x - mfx) ** 2 for x in fx))
    a_int = mfy - b_exp * mfx
    ss_tot = sum((y - mfy) ** 2 for y in fy)
    ss_res = sum((y - (a_int + b_exp * x)) ** 2 for x, y in zip(fx, fy))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    # dashed fit extended across the full visible x-axis
    fit_pts = " ".join(
        f"{xf(u):.1f},{yf(10 ** (a_int + b_exp * u)):.1f}"
        for u in (x0 + (x1 - x0) * i / 24 for i in range(25)))
    s.append(f"<polyline points='{fit_pts}' fill='none' stroke='#888' "
             f"stroke-width='1.6' stroke-dasharray='6 4'/>")

    for m in ORDER:
        cx, cy, col = xf(lx[m]), yf(yv[m]), COLOR[m]
        if ye[m] > 0:
            s.append(f"<line x1='{cx:.1f}' y1='{yf(yv[m]-ye[m]):.1f}' x2='{cx:.1f}' "
                     f"y2='{yf(yv[m]+ye[m]):.1f}' stroke='{col}' stroke-width='1.6'/>")
            for yy in (yf(yv[m] - ye[m]), yf(yv[m] + ye[m])):
                s.append(f"<line x1='{cx-5:.1f}' y1='{yy:.1f}' x2='{cx+5:.1f}' "
                         f"y2='{yy:.1f}' stroke='{col}' stroke-width='1.6'/>")
        s.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='6' fill='{col}' "
                 f"stroke='#222' stroke-width='1.4'/>")
    lxleg = w - pad_r + 18
    legend_models = list(reversed(ORDER))
    ly0 = pad_t + plot_h / 2 - (len(legend_models) - 1) * 13 - 22
    for i, m in enumerate(legend_models):
        ly = ly0 + i * 26
        s.append(f"<circle cx='{lxleg+5}' cy='{ly-3:.0f}' r='6' fill='{COLOR[m]}' "
                 f"stroke='#222' stroke-width='1.2'/>")
        s.append(f"<text x='{lxleg+18}' y='{ly+1:.0f}' font-size='11' fill='#444'>"
                 f"{m} <tspan fill='#999'>${SPEND_PER_MIN[m]:.2f}/min</tspan></text>")
    _fit_legend(s, lxleg, ly0 + len(legend_models) * 26 + 6, "$/min", b_exp, r2)
    s.append("</svg>")
    return "\n".join(s)


# --- plots 10-11: outcome polarization (squeezed vs dominant) ----------------

def plot_polarization(final_units: dict, plot_order: list, num: int,
                      order_label: str) -> str:
    """How each model's own nations end: a connected scatter of the fraction
    squeezed to <=3 units (circles) versus the fraction grown to >=6 units
    (squares), one point per model, two overplotted series colored by model.
    plot_order sets the left-to-right model order (e.g. by cost or by size)."""
    w, h = 760, 360
    pad_l, pad_b, pad_t, pad_r = 56, 50, 44, 170

    def rate(m, ok):
        v = final_units[m]
        return sum(1 for u in v if ok(u)) / len(v) if v else 0.0

    weak = {m: rate(m, lambda u: u <= 3) for m in ORDER}
    dom = {m: rate(m, lambda u: u >= 6) for m in ORDER}
    maxv = max(max(weak.values()), max(dom.values()))
    y1 = max(0.5, math.ceil((maxv + 0.05) * 10) / 10)
    plot_h = h - pad_b - pad_t

    def yf(v):
        return pad_t + plot_h * (1 - v / y1)

    slot = (w - pad_l - pad_r) / len(ORDER)
    xs = [pad_l + slot * (i + 0.5) for i in range(len(ORDER))]
    s = _svg_open(w, h, f"{num}. Squeezed vs dominant nations, ordered by {order_label}")

    for i in range(0, int(round(y1 * 10)) + 1):
        v = i / 10
        yy = yf(v)
        s.append(f"<line x1='{pad_l}' y1='{yy:.1f}' x2='{w-pad_r}' y2='{yy:.1f}' "
                 f"stroke='#eee' stroke-width='1'/>")
        s.append(f"<text x='{pad_l-8}' y='{yy+3:.1f}' text-anchor='end' "
                 f"font-size='10' fill='#999'>{v:.1f}</text>")
    s.append(f"<text x='16' y='{pad_t+plot_h/2:.0f}' font-size='10' fill='#777' "
             f"transform='rotate(-90 16 {pad_t+plot_h/2:.0f})' "
             f"text-anchor='middle'>fraction of this model's nations</text>")

    # dots colored by model; squeezed = circle on the red line, dominant = square
    # on the slate line
    SQ, DOM = "#c0392b", "#2c3e50"
    for dat, col in ((weak, SQ), (dom, DOM)):
        pts = " ".join(f"{x:.1f},{yf(dat[m]):.1f}" for x, m in zip(xs, plot_order))
        s.append(f"<polyline points='{pts}' fill='none' stroke='{col}' "
                 f"stroke-width='2' stroke-opacity='0.55'/>")
    for x, m in zip(xs, plot_order):  # squeezed: circle
        s.append(f"<circle cx='{x:.1f}' cy='{yf(weak[m]):.1f}' r='6.5' "
                 f"fill='{COLOR[m]}' stroke='#222' stroke-width='1.3'/>")
    for x, m in zip(xs, plot_order):  # dominant: square
        cy, r = yf(dom[m]), 6
        s.append(f"<rect x='{x-r:.1f}' y='{cy-r:.1f}' width='{2*r}' height='{2*r}' "
                 f"fill='{COLOR[m]}' stroke='#222' stroke-width='1.3'/>")
    for x, m in zip(xs, plot_order):
        s.append(f"<text x='{x:.0f}' y='{h-26}' text-anchor='middle' font-size='12' "
                 f"font-weight='600' fill='{COLOR[m]}'>{m}</text>")

    # legend at right: line color marks the series, marker shape echoes the plot
    lx = w - pad_r + 18
    ly0 = pad_t + plot_h / 2 - 15
    s.append(f"<line x1='{lx}' y1='{ly0}' x2='{lx+24}' y2='{ly0}' stroke='{SQ}' "
             f"stroke-width='2.5'/>")
    s.append(f"<circle cx='{lx+12}' cy='{ly0}' r='6' fill='#888' stroke='#222' "
             f"stroke-width='1.2'/>")
    s.append(f"<text x='{lx+34}' y='{ly0+4}' font-size='11' fill='#444'>"
             f"squeezed (≤3 units)</text>")
    ly1 = ly0 + 30
    s.append(f"<line x1='{lx}' y1='{ly1}' x2='{lx+24}' y2='{ly1}' stroke='{DOM}' "
             f"stroke-width='2.5'/>")
    s.append(f"<rect x='{lx+6}' y='{ly1-6}' width='12' height='12' fill='#888' "
             f"stroke='#222' stroke-width='1.2'/>")
    s.append(f"<text x='{lx+34}' y='{ly1+4}' font-size='11' fill='#444'>"
             f"dominant (≥6 units)</text>")
    s.append("</svg>")
    return "\n".join(s)


# --- per-model KPI table ----------------------------------------------------

def kpi_table(data: dict) -> str:
    raw, final = data["raw"], data["final"]
    cols = list(reversed(ORDER))  # cheap -> frontier, matching plot 1

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
        ("Support rate", lambda m: pct(raw[m]['support'], raw[m]['orders'])),
        ("Convoy rate", lambda m: pct(raw[m]['convoy'], raw[m]['orders'])),
        ("Uncoordinated convoys", lambda m: pct(raw[m]['convoy_uncoord'], raw[m]['orders'])),
        ("Move-support success", lambda m: pct(raw[m]['supp_move_ok'], raw[m]['supp_move'])),
        ("Uncoordinated supports", lambda m: pct(raw[m]['supp_uncoord'], raw[m]['supp_move'])),
        ("Illegal orders", lambda m: pct(raw[m]['illegal'], raw[m]['orders'])),
        ("Self-bounces / 100 orders",
         lambda m: f"{100*raw[m]['self_bounce']/raw[m]['orders']:.1f}" if raw[m]['orders'] else "n/a"),
        ("Total mistakes",
         lambda m: pct(raw[m]['illegal'] + raw[m]['self_bounce'] + raw[m]['supp_uncoord'],
                       raw[m]['orders'])),
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
        f"<p class='sub'>Opus (frontier), Haiku (small Claude), and MiMo (budget) each "
        f"rotate through all seven powers once, against a field of Sonnet on the other "
        f"four seats, counterbalancing board position across {n} ten-year games to "
        f"isolate the model from the nations it plays.</p>",

        "<figure><object type='image/svg+xml' data='final_centers.svg'></object>",
        "<figcaption><b>The ranking, at last.</b> Over a full 10-year game the models "
        "separate on territory: Opus averages 6.6 centers per nation, Sonnet 4.9, MiMo "
        "4.1, Haiku 3.7. Opus clears the field; the two budget models trail. Each test "
        "model plays every nation once (Sonnet, the field, plays four per game); bars "
        "are means with 1&sigma; standard-error whiskers.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='sc_trajectory.svg'></object>",
        "<figcaption><b>Opus pulls away.</b> The four climb out of the opening together "
        "and stay tangled until about 1905, when Opus diverges upward toward 6.6 centers "
        "while Sonnet plateaus near 4.9 and the two budget models stay locked at the "
        "bottom. The long game is what converts the frontier model's cleaner execution "
        "into a territorial lead, which the 3-year rotation was too short to "
        "show.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='threshold_trajectories.svg'></object>",
        "<figcaption><b>Dominant and squeezed games over time.</b> The same outcome "
        "split into two thresholds and tracked by year: the fraction of each model's "
        "games in which its nation is dominant (&ge;6 supply centers, left) or squeezed "
        "(&le;3, right). Opus's dominant share climbs steadily to ~0.7 while its squeezed "
        "share falls to zero; the budget models are the mirror, their dominant share "
        "barely lifts off the floor while their squeezed share stays high. Error bars are "
        "1&sigma; binomial standard error (&radic;(p(1&minus;p)/n)), wide for the "
        "single-seat test models (n=7) and tighter for the Sonnet field "
        "(n=28).</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='competence.svg'></object>",
        "<figcaption><b>Competence splits by tier, but not by price alone.</b> The two "
        "budget models post the highest illegal-order rates (MiMo 8.5%, Haiku 8.8%) "
        "against Sonnet's 3.7% and Opus's 4.8%, the geometry ceiling the self-play "
        "games predicted. Support rate exposes the real separation: Opus coordinates on "
        "35% of its orders, three to five times the others, and that ambition also "
        "gives it the most self-bounces and the lowest hold rate (least passive). The "
        "self-bounce paradox survives at scale, MiMo jams its own units zero times "
        "because it barely coordinates. Error bars are 1&sigma; Poisson (&radic;N on the "
        "event count); a zero count is drawn as a one-sided upper limit (&sigma; &lt; "
        "1). The convoy panels stay near-empty even over 10 years. Exact values are in "
        "the KPI table below.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='negotiation.svg'></object>",
        "<figcaption><b>Negotiation separates the personas.</b> Opus and MiMo talk the "
        "most per nation; Sonnet drives the hardest bargains (most conditional "
        "language); and Haiku is the alliance-talker (30% alliance language against "
        "Opus's 5%, the frontier model barely courts coalitions, it just coordinates "
        "units instead). Betrayal is fairly even across the field (3.6&ndash;5.2%). "
        "Same 1&sigma; Poisson error bars; betrayals are a keyword heuristic, so read "
        "them as order-of-magnitude.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='offence_defence_means.svg'></object>",
        "<figcaption><b>Mean offence vs defence, with error bars.</b> One point per "
        "model with horizontal and vertical 1&sigma; standard-error whiskers (offence "
        "rewards taking ground, defence rewards surviving attack; scoring from the "
        "canonical dashboard). Opus sits top-right, the most solid on defence; MiMo is "
        "the most exposed (lowest defence, dislodged most); Sonnet is cautious (lowest "
        "offence). Haiku swings the widest (the tall whisker), posting the highest "
        "offence on average yet finishing last on centers, it takes ground it cannot "
        "hold.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='cost_frontier.svg'></object>",
        "<figcaption><b>What does the money buy? Now, territory.</b> Each KPI against "
        "cost per nation-game on a log axis (MiMo $0.21, Haiku $1.04, Sonnet $3.22, "
        "Opus $20.18, a ~95&times; span). Unlike the 3-year near-tie, at 10 years final "
        "centers climb with spend, the frontier dollar buys real ground. But the "
        "frontier is not monotonic: Haiku is a value-trap, costing 5&times; MiMo yet "
        "winning fewer centers, so MiMo dominates it on both axes. Total mistakes and "
        "illegal-order rate are lowest for Sonnet, not the priciest model, Opus trades "
        "some cleanliness back for the ambition errors that come with coordinating "
        "far more.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='param_frontier.svg'></object>",
        "<figcaption><b>Does size predict territory? At 10 years, yes.</b> Final supply "
        "centers against total parameter count on a log axis. MiMo is a published "
        "311B-parameter MoE (so the budget model is cheap, not small); Anthropic "
        "discloses nothing for the Claude models, so their horizontal bars span the "
        "third-party guesses (Haiku ~20B, Sonnet ~1&ndash;2T, Opus ~1.5&ndash;5T, "
        "total). Vertical bars are 1&sigma; standard error on centers. Unlike the flat "
        "3-year result, the four points now trend upward, from Haiku (~20B, 3.7 "
        "centers) to Opus (~2.7T, 6.6), bigger models win more ground. The Haiku anchor "
        "at ~20B is what makes the slope visible; without it the lineup spanned only "
        "~10&times;. The dashed line is the best-fit power law (SC &#8733; "
        "params<sup>0.10</sup>, R&#178;&asymp;0.77 in log-log): a shallow exponent, so "
        "centers grow with scale but slowly, and Opus sits above the line, beating the "
        "trend. Read the x-axis as order-of-magnitude (and total, not active, "
        "params).</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='spend_frontier.svg'></object>",
        "<figcaption><b>And against spend rate.</b> The same supply-center outcome "
        "against each model's burn rate, dollars per minute of wall-clock in its "
        "10-year self-play game (MiMo $0.05, Haiku $0.23, Sonnet $0.75, Opus $7.51, a "
        "~145&times; span). Like size, spend rate is a property of the model rather "
        "than the matchup, and unlike the speculative parameter counts it is measured "
        "exactly. The points trend up the same way, best-fit power law SC &#8733; "
        "($/min)<sup>0.11</sup> (R&#178;&asymp;0.79): faster-and-pricier buys centers, "
        "but the shallow exponent says it buys them slowly, and Opus again sits above "
        "the line.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='polarization.svg'></object>",
        "<figcaption><b>How each model's own nations end: squeezed vs dominant.</b> "
        "The fraction of a model's nations that finish squeezed (&le;3 units, circles) "
        "versus dominant (&ge;6 units, squares); dots are colored by model, each series "
        "rides its own line, and the models run left to right by cost. The two fan "
        "apart by capability: Opus never ends squeezed and is dominant in 71% of its "
        "games; Haiku is the opposite, often squeezed and never dominant; MiMo swings "
        "to both extremes; Sonnet sits balanced between. No nation was eliminated "
        "outright in any of the seven ten-year games, so &le;3 units is the closest "
        "the rotation comes to a death count.</figcaption></figure>",

        "<figure><object type='image/svg+xml' data='polarization_by_size.svg'></object>",
        "<figcaption><b>The same, ordered by model size.</b> Identical data, but the "
        "models now run left to right by estimated parameter count (Haiku ~20B, MiMo "
        "311B, Sonnet ~1&ndash;2T, Opus ~1.5&ndash;5T) rather than by price. Reordered "
        "this way the dominant series climbs monotonically with scale, 0% (Haiku) "
        "&rarr; 29% (MiMo) &rarr; 39% (Sonnet) &rarr; 71% (Opus), the clearest "
        "statement in the study that board dominance tracks raw capacity, not cost "
        "(MiMo is far cheaper than Haiku yet larger, and it dominates more "
        "often).</figcaption></figure>",

        "<h2 style='font-size:17px;margin:36px 0 4px'>Per-model KPIs</h2>",
        "<p class='sub' style='margin:0 0 8px'>Every metric is normalised per nation "
        "(or as a share) so the four models compare despite Sonnet, the field, playing "
        "four nations per game to each test model's one.</p>",
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
    (out / "threshold_trajectories.svg").write_text(
        plot_threshold_trajectories(data["traj"]))
    (out / "competence.svg").write_text(plot_competence(data["raw"]))
    (out / "negotiation.svg").write_text(plot_negotiation(data["raw"]))
    (out / "offence_defence_means.svg").write_text(plot_od_means(data["od_points"]))
    (out / "cost_frontier.svg").write_text(plot_cost_frontier(data))
    (out / "param_frontier.svg").write_text(plot_param_frontier(data))
    (out / "spend_frontier.svg").write_text(plot_spend_frontier(data["final"]))
    cost_order = list(reversed(ORDER))                       # MiMo, Haiku, Sonnet, Opus
    size_order = sorted(ORDER, key=lambda m: PARAMS_B[m][1])  # Haiku, MiMo, Sonnet, Opus
    (out / "polarization.svg").write_text(
        plot_polarization(data["final_units"], cost_order, 10, "cost"))
    (out / "polarization_by_size.svg").write_text(
        plot_polarization(data["final_units"], size_order, 11, "model size"))
    (out / "index.html").write_text(build_index(data))
    # remove superseded artifacts
    for stale in ("offence_defence_bars.svg", "offence_defence.svg",
                  "offence_defence_paths.svg", "board_share.svg",
                  "province_share.svg"):
        (out / stale).unlink(missing_ok=True)

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
