"""Deterministic plain-English narration of a resolved phase.

Built straight from the library's orders + per-unit results — no LLM, so
it's faithful to ground truth, free, and reproducible. The same narration
is shown in the slideshow/report (human-facing) and fed into each agent's
prompt, so agents read what happened ("A KIE supports A HOL → BEL")
instead of decoding raw order syntax. Province codes are kept (the maps
label them); only the order *syntax* and the *outcomes* are spelled out.
"""
from __future__ import annotations

# Subset of diplomacy.utils.order_results tokens worth surfacing per order.
# (OK / '' = success, shown without annotation; 'dislodged' is handled
# separately since it describes the unit's fate, not its order's success.)
_RESULT_PHRASE = {
    "bounce": "bounced",
    "cut": "support cut",
    "void": "void",
    "no convoy": "no convoy",
    "disrupted": "disrupted",
}


def _english_order(order: str) -> str:
    """Render one order string in plain English (province codes kept)."""
    if order.strip().upper() == "WAIVE":
        return "waives a build"
    p = order.split()
    if len(p) < 2 or p[0] not in ("A", "F"):
        return order
    unit, rest = f"{p[0]} {p[1]}", p[2:]
    if "S" in rest:  # support (of a move or a hold)
        tail = " ".join(rest[rest.index("S") + 1:]).replace(" - ", " → ")
        return f"{unit} supports {tail}"
    if "C" in rest:  # convoy
        tail = " ".join(rest[rest.index("C") + 1:]).replace(" - ", " → ")
        return f"{unit} convoys {tail}"
    if "-" in rest:  # move
        return f"{unit} → {' '.join(rest[rest.index('-') + 1:])}"
    if "R" in rest:  # retreat
        return f"{unit} retreats → {' '.join(rest[rest.index('R') + 1:])}"
    if rest == ["H"]:
        return f"{unit} holds"
    if rest == ["B"]:
        return f"builds {unit}"
    if rest == ["D"]:
        return f"disbands {unit}"
    return order


def _acting_unit(order: str) -> str | None:
    p = order.split()
    return f"{p[0]} {p[1]}" if len(p) >= 2 and p[0] in ("A", "F") else None


def narrate_phase(
    orders: dict[str, list[str]],
    results: dict[str, list[str]],
    *,
    powers_order: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return [(power, one-line narration), ...] for powers that acted.

    `orders` maps power -> order strings; `results` maps a unit ("A BUD")
    -> result tokens (e.g. ["bounce"]). Each power's line lists its orders
    in plain English with outcome annotations, e.g.
    "A BUD → SER; F ALB supports A SER → GRE; A TYR → TRI (bounced)".
    """
    out: list[tuple[str, str]] = []
    for power in (powers_order or sorted(orders)):
        ods = orders.get(power) or []
        if not ods:
            continue
        frags, dislodged = [], []
        for o in ods:
            eng = _english_order(o)
            unit = _acting_unit(o)
            toks = results.get(unit, []) if unit else []
            notes = [_RESULT_PHRASE[t] for t in toks if t in _RESULT_PHRASE]
            if "dislodged" in toks and unit:
                dislodged.append(unit)
            if notes:
                eng += f" ({', '.join(notes)})"
            frags.append(eng)
        line = "; ".join(frags)
        if dislodged:
            line += f"  [dislodged: {', '.join(dislodged)}]"
        out.append((power, line))
    return out
