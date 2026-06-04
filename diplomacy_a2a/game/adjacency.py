"""Generate the standard Diplomacy adjacency table for the agent prompt.

Extracts adjacency data from Meta's `diplomacy` library, which is the same
data the adjudicator uses to validate orders. The table is formatted as
one line per location with explicit location-type annotations, optimized
for an LLM agent that needs to verify support and move legality.

The output is the body of the `## Adjacency table` section embedded in
the cached system prefix when the `--adjacency-table` flag is on
(default).
"""
from __future__ import annotations

from functools import lru_cache
from diplomacy import Game

from diplomacy_a2a.game.state import POWERS, POWER_ADJACENCY

# Multi-coast provinces on the standard map: armies move between any of
# their land-side neighbors regardless of coast, while fleets must specify
# a coast and follow only that coast's sea adjacencies.
_MULTI_COAST = ("STP", "SPA", "BUL")


def _loc_type(m, loc: str) -> str:
    """Human-readable type label for the adjacency-table entry."""
    if "/" in loc:
        return "fleet"
    t = m.loc_type.get(loc, "?").upper()
    if t == "WATER":
        return "water"
    if t == "COAST":
        return "coast"
    return "land"


def _army_adjacencies(m, prov: str) -> list[str]:
    """Compute army adjacency for a multi-coast province (STP, SPA, BUL).

    The library's `loc_abut` only populates coast entries (e.g.
    `loc_abut['STP/NC']`); the bare province returns None. But armies at
    these provinces can reach land-only neighbors (e.g. STP→MOS) that
    don't appear in either coast's fleet adjacency. Use `m.abuts()` to
    enumerate the true army-reachable set.
    """
    out: set[str] = set()
    for loc in m.locs:
        if loc == prov or "/" in loc:  # skip self and coast variants
            continue
        if m.abuts("A", prov, "-", loc):
            out.add(loc.upper())
    return sorted(out)


@lru_cache(maxsize=1)
def generate_adjacency_table() -> str:
    """Return the formatted adjacency table as a markdown section body.

    Cached so the table is computed once per process; it does not depend
    on game state.
    """
    g = Game()
    m = g.map

    lines: list[str] = [
        "Each entry below is `LOC (type): neighbors`.",
        "Types: **water** (sea/ocean, fleets only), **coast** (coastal land,",
        "armies and fleets), **land** (inland, armies only), **fleet** (a",
        "specific coast of a multi-coast province, fleet only).",
        "",
        "Multi-coast provinces (STP, SPA, BUL) appear as separate entries:",
        "the bare-province entry holds the army's adjacency (union of both",
        "coasts' land-side neighbors), while the /NC, /SC, /EC entries hold",
        "each coast's fleet adjacency.",
        "",
        "Adjacency is symmetric: if X is in Y's neighbors then Y is in X's.",
        "",
        "Worked support example: to verify `A PAR S A BUR - MUN` is legal,",
        "look up `PAR (land)`. Munich (`MUN`) must appear in PAR's neighbor",
        "list for the support to be legal. It does not, so that support is",
        "rejected by the adjudicator.",
        "",
    ]

    # Sort all entries alphabetically. For multi-coast provinces, emit the
    # army-view entry first, then the coast-specific fleet entries.
    seen: set[str] = set()
    all_keys: list[str] = []
    for loc in sorted(m.locs):
        # Group multi-coast: bare province before its /xx variants
        if "/" in loc:
            base = loc.split("/")[0]
            if base in _MULTI_COAST and base not in seen:
                all_keys.append(base)  # army-view first
                seen.add(base)
            all_keys.append(loc)
        else:
            if loc not in seen:
                all_keys.append(loc)
                seen.add(loc)

    for key in all_keys:
        if key in _MULTI_COAST:
            # Use m.abuts() to get the true army-adjacency set (the bare
            # province has no loc_abut entry; coast unions miss land-only
            # neighbors like STP-MOS).
            neighbors = _army_adjacencies(m, key)
            label = "army"
        else:
            # loc_abut mixes uppercase (fleet-adjacency) and lowercase
            # (army-only adjacency) entries. Normalize to uppercase: the
            # rare fleet-supports-via-land-only-adjacency case is left to
            # the adjudicator's adjacency check rather than burdening the
            # prompt with two notations.
            raw = m.loc_abut.get(key) or []
            neighbors = sorted({nb.upper() for nb in raw})
            label = _loc_type(m, key)
        nb_str = ", ".join(neighbors) if neighbors else "(none)"
        lines.append(f"- `{key}` ({label}): {nb_str}")

    return "\n".join(lines)


def generate_power_adjacency_table(power: str) -> str:
    """Format the full standard-map power-adjacency matrix for the prompt.

    Every agent sees every power's row, not just its own, so it can reason
    about third-party borders: which powers are positioned to open a second
    front on a rival that is pressuring it. The addressee's own row is marked
    `(you)`. Static and symmetric, so it lives in the cached system prefix.
    """
    lines = [
        "Which powers border which on the standard map (home regions).",
        "Adjacency is symmetric and fixed for the whole game. Beyond your own",
        "neighbors, use this to see who borders any other power, e.g. which",
        "powers are positioned to open a second front on a rival pressuring you.",
        "",
    ]
    for p in POWERS:
        you = " (you)" if p == power else ""
        lines.append(f"- {p}{you}: {', '.join(POWER_ADJACENCY[p])}")
    return "\n".join(lines)
