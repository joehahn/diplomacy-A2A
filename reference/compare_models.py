"""Cross-model gameplay comparison from finished transcripts.

Reads one or more ``transcript.jsonl`` files (each a complete self-play game
where a single model drives all seven powers) and prints a markdown table with
one column per model. Use it to eyeball which low-cost model plays best across
a handful of 10-year games.

    python reference/compare_models.py results/runA results/runB ...

Each argument is a run directory containing ``transcript.jsonl`` (or the file
itself). Metrics fall in three blocks:

  Board        N_eff, max SC, Land turnover. One reading per game, so treat
               as color at small sample sizes.
  Competence   per-order rates aggregated over hundreds of orders inside each
               game; these separate models even at one game apiece.
  Negotiation  message-derived signals; the project's actual deliverable, but
               heuristic and single-reading, so color rather than ranking.

The eight order/message metrics replicate the inline definitions in
``diplomacy_a2a/transcripts.py`` so this table agrees with each game's own
report. N_eff and dropped-turns are computed only here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Allow running as a script from anywhere: put the repo root on the path so the
# project package imports regardless of the current directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from diplomacy_a2a.runner import _estimate_cost  # noqa: E402

# Order/message regexes lifted verbatim from the dashboard so the numbers match.
COND_RE = re.compile(r"\b(if you|if I|in exchange|in return|provided that)\b", re.I)
ALLIANCE_RE = re.compile(
    r"\b("
    r"alliance|alliances|ally|allies|allied|"
    r"coalition|coalitions|"
    r"partner|partners|partnership|"
    r"pact|pacts|non-aggression|"
    r"coordinate|coordinated|coordination|"
    r"cooperate|cooperation"
    r")\b|work together|together against",
    re.I,
)
PROMISE_RE = re.compile(r"(won't|will not|stay out|no interest in|respect)", re.I)
STOP_WORDS = {
    "IF", "AND", "BUT", "THE", "OUR", "ALL", "HAS", "NOT", "NEW", "HOLD",
    "SC", "YOU", "FOR", "ARE", "WAS", "WHO", "WHY", "HOW", "OUT", "OWN",
}


def load_events(arg: str) -> list[dict]:
    path = Path(arg)
    if path.is_dir():
        path = path / "transcript.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _land_provinces() -> frozenset[str]:
    """Base codes of the 56 land provinces (LAND + COAST) from the map.

    Mirrors diplomacy_a2a/transcripts.py: coastal provinces count as land,
    the 19 pure-water provinces are excluded, sourced from the library.
    """
    from diplomacy import Map

    m = Map()
    return frozenset(
        loc.split("/")[0].upper()
        for loc in m.locs
        if m.area_type(loc) in ("LAND", "COAST")
    )


def land_turnover(events: list[dict]) -> int:
    """Land turnover ("changed hands"), replicating transcripts.py exactly.

    The occupier of a province is the power whose unit sits on it. Counts only
    direct power->other-power handovers of the 56 land provinces between
    consecutive post-adjudication snapshots; empty<->power moves do not count.
    A high total means a churning, contested board, so it pairs with N_eff to
    tell a balanced-and-dynamic game from a balanced-but-inert one. Distinct
    from supply-center ownership (which only flips at Fall).
    """
    land = _land_provinces()

    def prov(unit: str) -> str:
        loc = unit.split()[-1] if unit.split() else unit
        return loc.split("/")[0].upper()

    snaps: list[dict[str, str]] = []
    for e in events:
        if e.get("type") == "phase_resolved":
            occ: dict[str, str] = {}
            for power, units in (e.get("units", {}) or {}).items():
                for u in units:
                    p = prov(u)
                    if p in land:
                        occ[p] = power
            snaps.append(occ)
    total = 0
    prev = snaps[0] if snaps else {}
    for occ in snaps[1:]:
        for p, power in occ.items():
            before = prev.get(p)
            if before is not None and before != power:
                total += 1
        prev = occ
    return total


def support_breakdown(events: list[dict]) -> tuple[int, int, int, int]:
    """(move-supports, hold-supports, effective, uncoordinated) over movement phases.

    A support order ("X S Y - Z") is a move-support (offensive: backing an
    attack); "X S Y" is a hold-support (defensive: backing a unit in place). A
    move-support is effective when its supported move succeeds: the supported
    unit is not bounced/voided/dislodged and lands at its destination in the
    post-resolution board. It is uncoordinated when the supported move was never
    actually ordered (the unit Y was not ordered "Y - Z"): a self-coordination
    blunder, backing a move your own side never made.
    """
    resolved: dict[str, tuple[dict, set]] = {}
    move_targets: dict[str, set] = {}
    for e in events:
        if e.get("type") == "phase_resolved":
            res = e.get("results", {}) or {}
            locs = set()
            for units in (e.get("units", {}) or {}).values():
                for u in units:
                    t = u.split()
                    if len(t) >= 2:
                        locs.add((t[0], t[1].split("/")[0]))
            resolved[e.get("resolved_phase", "")] = (res, locs)
        elif e.get("type") == "orders_submitted" and e.get("phase", "").endswith("M"):
            tgt = move_targets.setdefault(e.get("phase", ""), set())
            for o in e.get("valid", []):
                if " - " in o and " S " not in o and " C " not in o:
                    left, right = o.split(" - ", 1)
                    lt, rt = left.split(), right.split()
                    if len(lt) >= 2 and rt:
                        tgt.add((lt[0], lt[1].split("/")[0], rt[0].split("/")[0]))
    move_s = hold_s = eff = uncoord = 0
    for e in events:
        if e.get("type") != "orders_submitted" or not e.get("phase", "").endswith("M"):
            continue
        res, locs = resolved.get(e.get("phase", ""), ({}, set()))
        tgt = move_targets.get(e.get("phase", ""), set())
        for o in e.get("valid", []):
            parts = o.split(" S ")
            if len(parts) != 2:
                continue
            supported = parts[1].strip()
            if " - " in supported:
                move_s += 1
                unit, dest = (s.strip() for s in supported.split(" - ", 1))
                ut = unit.split()
                if len(ut) >= 2 and (
                    ut[0], ut[1].split("/")[0], dest.split("/")[0]) not in tgt:
                    uncoord += 1
                failed = any(
                    tok in ("bounce", "void", "dislodged")
                    for tok in res.get(unit, ["void"])
                )
                landed = bool(unit.split()) and (
                    unit.split()[0],
                    dest.split("/")[0],
                ) in locs
                if not failed and landed:
                    eff += 1
            else:
                hold_s += 1
    return move_s, hold_s, eff, uncoord


def self_bounces(events: list[dict]) -> int:
    """Count self-inflicted standoffs: a power's move that bounced into a
    province its own side occupies after the phase resolves (moving into your
    own unit, or two of your units competing for one square). A legal order, so
    it never shows as illegal; it measures spatial self-coherence, the kind of
    blunder a careful player avoids.
    """
    post_occ: dict[str, dict[str, str]] = {}
    results: dict[str, dict] = {}
    for e in events:
        if e.get("type") == "phase_resolved":
            rp = e.get("resolved_phase", "")
            results[rp] = e.get("results", {}) or {}
            occ: dict[str, str] = {}
            for pw, units in (e.get("units", {}) or {}).items():
                for u in units:
                    t = u.split()
                    if len(t) >= 2:
                        occ[t[1].split("/")[0]] = pw
            post_occ[rp] = occ
    n = 0
    for e in events:
        if e.get("type") != "orders_submitted" or not e.get("phase", "").endswith("M"):
            continue
        ph, power = e.get("phase", ""), e.get("power", "")
        res, occ = results.get(ph, {}), post_occ.get(ph, {})
        for o in e.get("valid", []):
            if " - " not in o or " S " in o or " C " in o:
                continue
            unit = o.split(" - ", 1)[0].strip()
            dest = o.split(" - ", 1)[1].split()[0].split("/")[0]
            if any("bounce" in t for t in res.get(unit, [])) and occ.get(dest) == power:
                n += 1
    return n


def n_eff(centers: dict[str, list[str]]) -> float:
    """Effective number of powers: (sum SC)^2 / sum(SC^2), in [1, 7].

    1 means one power owns the board; 7 means all powers hold equal centers.
    A model that lets one nation run away scores low.
    """
    counts = [len(v) for v in centers.values()]
    sq = sum(c * c for c in counts)
    if sq == 0:
        return 0.0
    total = sum(counts)
    return total * total / sq


def metrics(events: list[dict]) -> dict:
    run_started = next((e for e in events if e.get("type") == "run_started"), {})
    run_ended = next((e for e in events if e.get("type") == "run_ended"), {})

    # --- order rates over all movement-phase orders (invalid in denominator) ---
    total = holds = supports = convoys = illegal = adjacency = 0
    for e in events:
        if e.get("type") == "orders_submitted" and e.get("phase", "").endswith("M"):
            for o in e.get("valid", []):
                total += 1
                s = o.rstrip()
                if s.endswith(" H"):
                    holds += 1
                elif re.search(r"\bS\b", o):
                    supports += 1
                elif re.search(r"\bC\b", o) or s.endswith(" VIA"):
                    convoys += 1
            for inv in e.get("invalid", []):
                total += 1
                illegal += 1
                if re.search(r"\bS\b", inv) or (
                    " - " in inv
                    and not re.search(r"\bC\b", inv)
                    and not inv.endswith(" VIA")
                ):
                    adjacency += 1

    # --- dropped turns (NMR): units that entered a movement phase with no order ---
    # Units entering a phase come from the prior resolution's snapshot, keyed by
    # its next_phase. The opening movement phase has no prior snapshot and is
    # skipped, so this slightly undercounts; it still flags a model that leaves
    # units unordered.
    units_entering: dict[str, dict[str, int]] = {}
    for e in events:
        if e.get("type") == "phase_resolved":
            nxt = e.get("next_phase", "")
            units_entering[nxt] = {
                p: len(u) for p, u in (e.get("units", {}) or {}).items()
            }
    dropped = expected_units = 0
    for e in events:
        if e.get("type") == "orders_submitted" and e.get("phase", "").endswith("M"):
            exp = units_entering.get(e.get("phase", ""), {}).get(e.get("power", ""))
            if exp is None:
                continue
            submitted = len(e.get("valid", [])) + len(e.get("invalid", []))
            dropped += max(0, exp - submitted)
            expected_units += exp

    # --- board concentration from supply-center snapshots ---
    centers_snaps = [
        e.get("centers", {}) for e in events if e.get("type") == "phase_resolved"
    ]
    final_centers = centers_snaps[-1] if centers_snaps else {}
    neff_final = n_eff(final_centers) if final_centers else 0.0
    sc_counts = {p: len(v) for p, v in final_centers.items()}
    max_sc = max(sc_counts.values(), default=0)
    turnover = land_turnover(events)

    # --- negotiation signals over all messages ---
    msgs = cond = alliance = 0
    for e in events:
        if e.get("type") == "agent_messages":
            for _, text in (e.get("messages", {}) or {}).items():
                msgs += 1
                if COND_RE.search(text):
                    cond += 1
                if ALLIANCE_RE.search(text):
                    alliance += 1

    orders_by_phase: dict[str, dict[str, list[str]]] = {}
    for e in events:
        if e.get("type") == "orders_submitted":
            orders_by_phase.setdefault(e["phase"], {})[e["power"]] = e.get("valid", [])
    seen: set[tuple[str, str, str]] = set()
    betrayals = 0
    for e in events:
        if e.get("type") != "agent_messages":
            continue
        phase, speaker = e.get("phase", ""), e.get("power", "")
        speaker_orders = orders_by_phase.get(phase, {}).get(speaker, [])
        for _, text in (e.get("messages", {}) or {}).items():
            if not PROMISE_RE.search(text):
                continue
            provs = {
                p for p in re.findall(r"\b([A-Z]{3})\b", text) if p not in STOP_WORDS
            }
            for prov in provs:
                key = (phase, speaker, prov)
                if key in seen:
                    continue
                for o in speaker_orders:
                    m = re.match(r"[AF] \S+\s*-\s*(\S+)", o)
                    if m and m.group(1).split("/")[0] == prov:
                        betrayals += 1
                        seen.add(key)
                        break

    def pct(n: int, d: int) -> float:
        return 100 * n / d if d else 0.0

    supp_move, supp_hold, supp_eff, supp_uncoord = support_breakdown(events)
    return {
        "model": run_started.get("model", "?"),
        "phases": run_ended.get("phases_played", "?"),
        "cost": _estimate_cost(run_ended.get("tokens_by_model", {}) or {}),
        "elapsed_min": (run_ended.get("elapsed_seconds", 0) or 0) / 60,
        "neff_final": neff_final,
        "max_sc": max_sc,
        "turnover": turnover,
        "orders": total,
        "illegal": pct(illegal, total),
        "adjacency": pct(adjacency, total),
        "dropped": pct(dropped, expected_units),
        "holds": pct(holds, total),
        "supports": pct(supports, total),
        "supp_move": pct(supp_move, total),
        "supp_hold": pct(supp_hold, total),
        "supp_eff": pct(supp_eff, supp_move),
        "supp_bounced": pct(supp_move - supp_eff - supp_uncoord, supp_move),
        "supp_uncoord": pct(supp_uncoord, supp_move),
        "convoys": pct(convoys, total),
        "self_bounces": self_bounces(events),
        "msgs": msgs,
        "cond": pct(cond, msgs),
        "alliance": pct(alliance, msgs),
        "betrayals": betrayals,
    }


# (label, key, formatter). None label starts a new section header.
ROWS = [
    ("Cost & runtime", None, None),
    ("Cost (USD)", "cost", "${:.2f}"),
    ("Wall-clock (min)", "elapsed_min", "{:.1f}"),
    ("Phases played", "phases", "{}"),
    ("Board", None, None),
    ("N_eff (final)", "neff_final", "{:.2f}"),
    ("Max SC (final)", "max_sc", "{}"),
    ("Land turnover", "turnover", "{}"),
    ("Competence", None, None),
    ("Total orders", "orders", "{}"),
    ("Illegal %", "illegal", "{:.1f}"),
    ("Adjacency %", "adjacency", "{:.1f}"),
    ("Dropped turns %", "dropped", "{:.1f}"),
    ("Hold %", "holds", "{:.1f}"),
    ("Support %", "supports", "{:.1f}"),
    ("Support move %", "supp_move", "{:.1f}"),
    ("Support hold %", "supp_hold", "{:.1f}"),
    ("Support eff %", "supp_eff", "{:.1f}"),
    ("Support bounced %", "supp_bounced", "{:.1f}"),
    ("Support uncoord %", "supp_uncoord", "{:.1f}"),
    ("Convoy %", "convoys", "{:.1f}"),
    ("Self-bounces", "self_bounces", "{}"),
    ("Negotiation", None, None),
    ("Messages", "msgs", "{}"),
    ("Bargaining %", "cond", "{:.1f}"),
    ("Alliances %", "alliance", "{:.1f}"),
    ("Betrayals", "betrayals", "{}"),
]


def render(rows: list[dict]) -> str:
    headers = [r["model"] for r in rows]
    width = max([len("Metric")] + [len(s) for s, _, _ in ROWS])
    cols = [max(len(h), 8) for h in headers]
    out = []
    head = "| " + "Metric".ljust(width) + " | "
    head += " | ".join(h.rjust(c) for h, c in zip(headers, cols)) + " |"
    out.append(head)
    out.append("|" + "-" * (width + 2) + "|" + "|".join("-" * (c + 2) for c in cols) + "|")
    for label, key, fmt in ROWS:
        if key is None:
            out.append("| **" + label + "**".ljust(width - len(label) + 2) + " | "
                       + " | ".join("".rjust(c) for c in cols) + " |")
            continue
        cells = []
        for r, c in zip(rows, cols):
            v = r[key]
            cells.append(fmt.format(v).rjust(c))
        out.append("| " + label.ljust(width) + " | " + " | ".join(cells) + " |")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    rows = [metrics(load_events(a)) for a in argv]
    rows.sort(key=lambda r: r["cost"])  # columns ordered cheapest to priciest
    print(render(rows))
    print()
    print("N_eff and dropped-turns are reference-only; all other metrics mirror")
    print("diplomacy_a2a/transcripts.py. Board and negotiation blocks are")
    print("single-reading per game; rank on the competence block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
