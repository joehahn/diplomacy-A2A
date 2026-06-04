# results/canonical/

The published demo runs. These are committed to the repo so visitors
can read the interesting output without spending money on API calls.

## `20260601T214429Z/`: current canonical (10-year)

```bash
python -m diplomacy_a2a run --log-prompts --with-commentary --category canonical
```

Sonnet 4.6, 10 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, uniform baseline persona across all 7 powers,
plus the LLM-commentary post-pass. 33 phases, **≈$24 / ≈31 min** (parallel
per-power LLM fan-out).

Final standings at S1911M (no solo win, played to the 10-year cap;
Turkey eliminated at F1906M):

| Power | SC count | Centers |
|---|---:|---|
| Germany | 8 | BEL, BER, DEN, HOL, KIE, MUN, NWY, SWE |
| France  | 6 | BRE, MAR, PAR, POR, SPA, TUN |
| Italy   | 6 | ANK, BUL, NAP, ROM, SMY, VEN |
| Russia  | 6 | CON, MOS, RUM, SEV, STP, WAR |
| Austria | 5 | BUD, GRE, SER, TRI, VIE |
| England | 3 | EDI, LON, LVP |
| Turkey  | 0 | (eliminated) |

Italy occupies Ankara and Smyrna (Turkey's traditional home centers);
Russia holds Constantinople. Germany surges from 2 SCs in F1902M to 8 by
F1910M, becoming the dominant power.

[**View this run's turn-by-turn dashboard**](https://joehahn.github.io/diplomacy-A2A/results/canonical/20260601T214429Z/dashboard/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.
