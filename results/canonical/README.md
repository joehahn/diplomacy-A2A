# results/canonical/

The published demo runs. These are committed to the repo so visitors
can read the interesting output without spending money on API calls.

## `2026-06-04.04.00.49/`: current canonical (10-year)

```bash
python -m diplomacy_a2a run --log-prompts --with-commentary --category canonical
```

Sonnet 4.6, 10 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, uniform baseline persona across all 7 powers,
plus the LLM-commentary post-pass. 36 phases, **≈$24 / ≈33 min** (parallel
per-power LLM fan-out).

Final standings at W1910A (no solo win, played to the 10-year cap; Germany
eliminated at F1908M):

| Power | SC count | Centers |
|---|---:|---|
| England | 8 | BEL, DEN, EDI, HOL, LON, LVP, NWY, SWE |
| France  | 7 | BRE, KIE, MAR, MUN, PAR, POR, SPA |
| Russia  | 6 | BER, MOS, RUM, SEV, STP, WAR |
| Italy   | 5 | GRE, NAP, ROM, TUN, VEN |
| Austria | 4 | BUD, SER, TRI, VIE |
| Turkey  | 4 | ANK, BUL, CON, SMY |
| Germany | 0 | (eliminated) |

England climbed steadily on a durable Anglo-Russian northern freeze, taking
Belgium, Norway, Sweden, Holland and Kiel while rarely fighting, and finished
the clear leader at 8. Germany was carved up early, lost Munich and Holland by
1903, clung to a single center for years (briefly clawing Munich back with
Russian help), and was eliminated at F1908M when France took Kiel with
England's consent and held Munich; its home centers ended split (France holds
Kiel and Munich, Russia holds Berlin). France rode the German collapse to 7,
while the Austria-Italy Balkan partnership ground down Turkey, whose
double-supported Bulgaria repelled assault after assault, leaving Turkey alive
at 4.

[**View this run's turn-by-turn dashboard**](https://joehahn.github.io/diplomacy-A2A/results/canonical/2026-06-04.04.00.49/dashboard/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.

The previous 10-year canonical (`2026-06-04.01.23.15/`) is retained alongside
this one as the pre-prompt-revision baseline; REFERENCE.md's wall-time table
compares the two.
