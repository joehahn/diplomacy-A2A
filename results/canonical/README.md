# results/canonical/

The published demo runs. These are committed to the repo so visitors
can read the interesting output without spending money on API calls.

## `2026-06-04.01.23.15/`: current canonical (10-year)

```bash
python -m diplomacy_a2a run --log-prompts --with-commentary --category canonical
```

Sonnet 4.6, 10 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, uniform baseline persona across all 7 powers,
plus the LLM-commentary post-pass. 35 phases, **≈$25 / ≈34 min** (parallel
per-power LLM fan-out).

Final standings at W1910A (no solo win, played to the 10-year cap; all
seven powers survive):

| Power | SC count | Centers |
|---|---:|---|
| Austria | 6 | BUD, BUL, RUM, SER, TRI, VIE |
| France  | 6 | BEL, BRE, MAR, PAR, POR, SPA |
| Russia  | 6 | CON, MOS, SEV, STP, SWE, WAR |
| England | 5 | DEN, EDI, LON, LVP, NWY |
| Italy   | 5 | GRE, NAP, ROM, TUN, VEN |
| Germany | 4 | BER, HOL, KIE, MUN |
| Turkey  | 2 | ANK, SMY |

Russia broke out fastest (6 centers by the end of 1901) and led the board
for most of the game, playing its Balkan neighbors against each other over
Bulgaria and Greece. The center of the board congealed into a long
stalemate: the Anglo-French coalition telegraphed an attack on Germany
nearly every year from 1902 on, yet bounced off Germany's
Holland-Belgium-Munich defense until it finally cracked in 1910. Turkey,
squeezed from all sides and stripped of its fleets, bled from four centers
down to its two original home centers (Russia took Constantinople, Austria
took Bulgaria). With no power ever assembling a durable winning alliance,
the game ended balanced and undecided: a three-way tie at six between
Austria, France, and Russia.

[**View this run's turn-by-turn dashboard**](https://joehahn.github.io/diplomacy-A2A/results/canonical/2026-06-04.01.23.15/dashboard/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.

The previous 10-year canonical (`20260601T214429Z/`) is retained alongside
this one; REFERENCE.md cites its measurements in the wall-time and findings
sections.
