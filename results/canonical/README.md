# results/canonical/

The published demo run. Committed to the repo so visitors can read the
interesting output without spending money on API calls.

## `2026-06-04.14.48.20/`: current canonical (10-year)

```bash
python -m diplomacy_a2a run --log-prompts --with-commentary --category canonical
```

Sonnet 4.6, 10 game-years, 3 negotiation rounds per movement phase, agent
memory = 3 movement turns, self-authored strategy notes on, prompt+response
dump for the first game-year, uniform baseline persona across all 7 powers,
plus the LLM-commentary post-pass. 41 phases, **≈$26 / ≈34 min** (parallel
per-power LLM fan-out). This run uses the expansion-oriented prompt; its
play is markedly more aggressive than earlier canonicals (hold rate under
50%, more dislodgements and betrayals; see REFERENCE.md's prompt-revision
comparison).

Final standings at W1910A (no solo win, played to the 10-year cap; no
eliminations):

| Power | SC count | Centers |
|---|---:|---|
| England | 8 | DEN, EDI, KIE, LON, LVP, NWY, STP, SWE |
| France  | 7 | BEL, BRE, MAR, MUN, PAR, POR, SPA |
| Italy   | 6 | NAP, ROM, TRI, TUN, VEN, VIE |
| Turkey  | 6 | ANK, BUL, CON, GRE, RUM, SMY |
| Russia  | 4 | BER, MOS, SEV, WAR |
| Austria | 2 | BUD, SER |
| Germany | 1 | HOL |

England built an early lead off Scandinavia and the north (reaching 8 by
mid-game, eventually taking Russia's St. Petersburg and Germany's Kiel), but
never ran away with it, because the strongest players kept attacking each
other instead of consolidating. The mid-to-late game was a multi-front grind:
a Franco-Russian squeeze dislodged England's fleet from Holland at F1907M,
but the anti-leader coalitions repeatedly frayed (at S1910M France pocketed
Munich and Belgium for itself instead of joining Russia's attack on Kiel).
Italy ground into Austria's home (taking Trieste and Vienna), Austria stabbed
Turkey for Constantinople and was later reduced to 2, Turkey clawed back up to
6, and Germany clung to a single center. With damage diffused across all
seven survivors, the game ended spread and undecided.

[**View this run's turn-by-turn dashboard**](https://joehahn.github.io/diplomacy-A2A/results/canonical/2026-06-04.14.48.20/dashboard/index.html)
(GitHub Pages) to flip through the maps, narration, commentary, agent
strategies, and dialogue.
