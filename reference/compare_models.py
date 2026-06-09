"""Cross-model gameplay comparison from finished transcripts.

Reads one or more ``transcript.jsonl`` files (each a complete self-play game
where a single model drives all seven powers) and prints a markdown table with
one column per model. Use it to eyeball which low-cost model plays best across
a handful of 10-year games.

    python reference/compare_models.py results/runA results/runB ...

Each argument is a run directory containing ``transcript.jsonl`` (or the file
itself). Metrics fall in three blocks:

  Board        N_eff, max SC, survivors, centers held. One reading per game,
               so treat as color at small sample sizes.
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
    survivors = sum(1 for c in sc_counts.values() if c > 0)
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

    return {
        "model": run_started.get("model", "?"),
        "phases": run_ended.get("phases_played", "?"),
        "cost": _estimate_cost(run_ended.get("tokens_by_model", {}) or {}),
        "elapsed_min": (run_ended.get("elapsed_seconds", 0) or 0) / 60,
        "neff_final": neff_final,
        "max_sc": max_sc,
        "survivors": survivors,
        "turnover": turnover,
        "orders": total,
        "illegal": pct(illegal, total),
        "adjacency": pct(adjacency, total),
        "dropped": pct(dropped, expected_units),
        "holds": pct(holds, total),
        "supports": pct(supports, total),
        "convoys": pct(convoys, total),
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
    ("Survivors", "survivors", "{}"),
    ("Land turnover", "turnover", "{}"),
    ("Competence", None, None),
    ("Total orders", "orders", "{}"),
    ("Illegal %", "illegal", "{:.1f}"),
    ("Adjacency %", "adjacency", "{:.1f}"),
    ("Dropped turns %", "dropped", "{:.1f}"),
    ("Hold %", "holds", "{:.1f}"),
    ("Support %", "supports", "{:.1f}"),
    ("Convoy %", "convoys", "{:.1f}"),
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
    print(render(rows))
    print()
    print("N_eff and dropped-turns are reference-only; all other metrics mirror")
    print("diplomacy_a2a/transcripts.py. Board and negotiation blocks are")
    print("single-reading per game; rank on the competence block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
