"""Wrapper around `diplomacy.Game` — our orchestration's only contact
with the adjudicator library.

The library's default rule set includes NO_PRESS and SOLITAIRE, which
disable negotiation and assume a single-player simulation. We strip
those for full-press (negotiation-enabled) play but keep the rest of
the defaults that govern timing/dummy-power behavior.

All adjudication (support cutting, convoys, dislodgments, retreats,
builds) is delegated to the library — never reimplemented here.
"""
from __future__ import annotations

from dataclasses import dataclass

from diplomacy import Game

# Library defaults minus NO_PRESS (allow private messaging) and
# SOLITAIRE (allow multiple controlled powers).
FULL_PRESS_RULES = [
    "NO_DEADLINE",
    "CD_DUMMIES",
    "ALWAYS_WAIT",
    "POWER_CHOICE",
]

POWERS = ("AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY")

# Canonical great-power adjacency on the standard map: whose home regions
# border whose. Static (these structural relationships hold all game) and
# symmetric. Gives each agent a stable read on its natural rivals (adjacent)
# versus the distant powers it can court for a second front (non-adjacent).
POWER_ADJACENCY: dict[str, tuple[str, ...]] = {
    "AUSTRIA": ("GERMANY", "ITALY", "RUSSIA", "TURKEY"),
    "ENGLAND": ("FRANCE", "GERMANY", "RUSSIA"),
    "FRANCE": ("ENGLAND", "GERMANY", "ITALY"),
    "GERMANY": ("AUSTRIA", "ENGLAND", "FRANCE", "ITALY", "RUSSIA"),
    "ITALY": ("AUSTRIA", "FRANCE", "GERMANY"),
    "RUSSIA": ("AUSTRIA", "ENGLAND", "GERMANY", "TURKEY"),
    "TURKEY": ("AUSTRIA", "RUSSIA"),
}


@dataclass
class GameState:
    """Thin facade over `diplomacy.Game` with the methods our orchestration needs."""

    game: Game

    @classmethod
    def new(cls) -> "GameState":
        return cls(game=Game(rules=list(FULL_PRESS_RULES)))

    @property
    def phase(self) -> str:
        """Long-form phase, e.g. 'SPRING 1901 MOVEMENT'."""
        return self.game.phase

    @property
    def short_phase(self) -> str:
        """Compact phase code, e.g. 'S1901M'."""
        return self.game.get_current_phase()

    @property
    def is_done(self) -> bool:
        return bool(self.game.is_game_done)

    def units(self, power: str) -> list[str]:
        return list(self.game.powers[power].units)

    def centers(self, power: str) -> list[str]:
        return list(self.game.powers[power].centers)

    def all_units(self) -> dict[str, list[str]]:
        return {p: self.units(p) for p in POWERS}

    def all_centers(self) -> dict[str, list[str]]:
        return {p: self.centers(p) for p in POWERS}

    def dislodged(self, power: str) -> dict[str, list[str]]:
        """{unit_loc: [valid_retreat_provinces]} for units that must retreat."""
        return dict(self.game.get_state().get("retreats", {}).get(power, {}))

    def legal_orders(self, power: str) -> dict[str, list[str]]:
        """{location: [legal_order_strings]} filtered to this power's orderables."""
        all_possible = self.game.get_all_possible_orders()
        return {loc: list(all_possible.get(loc, [])) for loc in self.game.get_orderable_locations(power)}

    def submit(self, power: str, orders: list[str]) -> None:
        self.game.set_orders(power, orders)

    def advance(self) -> None:
        """Process the current phase (adjudicate orders, advance to next)."""
        self.game.process()

    def recent_resolved(
        self, n: int = 1
    ) -> list[tuple[str, dict[str, list[str]], dict[str, list[str]]]]:
        """Resolved phases covering the last `n` movement-turn cycles.

        Walks history backward and includes phases until it has passed N
        movement phases — so a cycle is "the movement plus its trailing
        retreats and adjustments." Returned in chronological order, each
        entry is (short_phase, orders_by_power, results_by_unit). Results
        carry adjudication outcomes (bounce, dislodged, …) that bare orders
        don't. `n == 0` returns an empty list (memoryless).
        """
        if n <= 0:
            return []
        history = self.game.get_phase_history()
        out: list[tuple[str, dict[str, list[str]], dict[str, list[str]]]] = []
        movements_collected = 0
        for ph in reversed(history):
            orders = {p: list(o) for p, o in ph.orders.items() if o}
            results = {u: [str(t) for t in r] for u, r in ph.results.items()}
            out.append((ph.name, orders, results))
            if ph.name.endswith("M"):
                movements_collected += 1
                if movements_collected >= n:
                    break
        return list(reversed(out))
