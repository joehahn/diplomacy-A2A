# Model comparison: Sonnet vs DeepSeek

One 10-year self-play game per model (a single model drives all seven powers).
Game-level rows are n=1, so read the Board and Negotiation blocks as color and
rank on the Competence block, where each rate averages over hundreds of orders.

Runs compared:

- `claude-sonnet-4-6`: `results/canonical/2026-06-04.14.48.20`
- `deepseek/deepseek-v4-flash`: `results/axis_a/2026-06-09.00.29.32`

Regenerate this table (and pass any number of run dirs to add models or seeds):

```
python reference/compare_models.py \
  results/canonical/2026-06-04.14.48.20 \
  results/axis_a/2026-06-09.00.29.32
```

## Comparison

| Metric                | claude-sonnet-4-6 | deepseek/deepseek-v4-flash |
|-----------------------|-------------------|----------------------------|
| **Cost & runtime**        |                   |                            |
| Cost (USD)            |            $25.62 |                      $1.17 |
| Wall-clock (min)      |              34.0 |                       54.5 |
| Phases played         |                41 |                         36 |
| **Board**                 |                   |                            |
| N_eff (final)         |              5.61 |                       6.02 |
| N_eff (min over game) |              5.61 |                       5.78 |
| Max SC (final)        |                 8 |                          9 |
| Survivors             |                 7 |                          7 |
| Centers held /34      |                34 |                         34 |
| Land turnover         |                27 |                         12 |
| **Competence**            |                   |                            |
| Total orders          |               640 |                        626 |
| Illegal %             |               3.1 |                        7.0 |
| Adjacency %           |               3.1 |                        6.4 |
| Dropped turns %       |               0.2 |                        0.7 |
| Hold %                |              49.4 |                       59.4 |
| Support %             |              14.5 |                        7.5 |
| Convoy %              |               0.3 |                        2.6 |
| **Negotiation**           |                   |                            |
| Messages              |              1034 |                       1359 |
| Bargaining %          |              55.2 |                       48.5 |
| Alliances %           |              18.8 |                       26.3 |
| Betrayals             |                47 |                         37 |

N_eff and dropped-turns are reference-only; all other metrics mirror
diplomacy_a2a/transcripts.py. Board and negotiation blocks are
single-reading per game; rank on the competence block.

## Reading

- **Cost:** DeepSeek runs at ~1/22 the dollar cost but ~1.6x the wall-clock
  (no gateway prompt caching, higher per-call latency, empty-content retries).
- **Competence (trustworthy):** Sonnet is the stronger player: half the illegal
  rate, twice the coordination (Support), and less passive (lower Hold).
- **Board (color):** DeepSeek's higher N_eff is inertia, not skill: its board
  changed hands less than half as often (Land turnover 12 vs 27).
- **Verdict:** DeepSeek V4-Flash is the viable low-cost alternative (Kimi and
  Gemini both land near $20/game). It plays a coherent but weaker, more passive
  game for a fraction of the cost.
