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

    def recent_resolved(self) -> list[tuple[str, dict[str, list[str]], dict[str, list[str]]]]:
        """Resolved phases since (and including) the most recent movement phase.

        Returns, in chronological order, (short_phase, orders_by_power,
        results_by_unit) for the last "turn cycle" — i.e. the latest
        movement phase plus any retreat/adjustment phases after it. This is
        the "what just happened" recap an agent needs; results carry the
        adjudication outcomes (bounce, dislodged, …) that bare orders don't.
        """
        history = self.game.get_phase_history()
        out: list[tuple[str, dict[str, list[str]], dict[str, list[str]]]] = []
        for ph in reversed(history):
            orders = {p: list(o) for p, o in ph.orders.items() if o}
            results = {u: [str(t) for t in r] for u, r in ph.results.items()}
            out.append((ph.name, orders, results))
            if ph.name.endswith("M"):  # stop once we've included a movement phase
                break
        return list(reversed(out))
