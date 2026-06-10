# REFERENCE.md — technical details, data, and experiment results

The README's job is to tell a first-time visitor what this project is and why
it's interesting. This file is for the underlying technical material: model
pricing, observed timing, quality observations, and the controlled-variation
experiment results as they accumulate.

Links back to [README.md](README.md) and [results/README.md](results/README.md).

---

## Anthropic per-million-token rates (used by the cost estimator)

The runner's cost estimator (`runner._RATE_TABLE`) keys on a model-id prefix
and assumes the published list pricing. Rerunning a committed game gives you
the same `cost_usd` because adjudication and token counts are deterministic
from the recorded orders + dialogue.

| Family prefix | Input | Output | Cache write | Cache read |
|---|---:|---:|---:|---:|
| `claude-sonnet-4-6` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-opus-4-7`   | $15.00 | $75.00 | $18.75 | $1.50 |
| `claude-opus-4-8`   | $15.00 | $75.00 | $18.75 | $1.50 |
| `claude-haiku-4-5`  | $1.00 | $5.00 | $1.25 | $0.10 |

Anything that doesn't prefix-match falls back to the Sonnet row — so unknown
models are *over-estimated*, not silently under-estimated.

Anthropic's **prompt caching** is on by default
([`AnthropicClient`](diplomacy_a2a/llm/anthropic_client.py) sets
`cache_control: ephemeral` on the system prompt) — for a 2-year Sonnet game
this saves ≈22% ($0.69 of $3.12) by serving the rules + persona prefix as
cache reads (10% of input price) after the first write. The fix to make
the estimator **model-aware** landed in commit `7358cdd`; before that,
mixed-model and Haiku-only games reported Sonnet-rate-inflated costs.

---

## Per-phase wall-time observations

All rows except the last are serial (one per-power LLM call at a time
within each phase); the parallel fan-out landed in commit `1b2a19b`
and divides per-phase wall time by ≈4× on observed Haiku numbers
(see the last row vs the serial Haiku plain-vanilla baseline on the
row above).

| Run | Model | Settings | Phases | Total time | **s / phase** | Cost reported |
|---|---|---|---:|---:|---:|---:|
| 20260524T031616Z | Sonnet | no negotiation | 7 | – | – | $0.35 |
| 20260524T034819Z | Sonnet | 1 round, 2 yr | 7 | – | – | $0.88 |
| 20260527T184246Z | Sonnet | 3 rounds, 2 yr, `--log-prompts` | 8 | 1419s | **≈177** | $2.43 |
| 20260528T214253Z *(deleted; previous canonical)* | Sonnet | 3 rounds, 2 yr, strategy notes, `--log-prompts` | 7 | 1713s | **≈245** | $3.20 |
| 20260528T213153Z (smoke) | Haiku | 1 round, 1 yr, strategy notes | 3 | 214s | **≈71** | $0.85 *(Sonnet-inflated; actual ≈ $0.28)* |
| 20260527T132540Z (smoke) | Haiku | 1 round, 1 yr | 3 | 180s | **≈60** | $0.46 *(actual ≈ $0.15)* |
| 20260529T151442Z *(partial, credit-out)* | Haiku | 3 rounds, 5 yr, strategy notes, `--log-prompts-years 5` | 13 of ≈17 | ≈3300s | **≈252** | – |
| 20260529T191351Z (plain-vanilla baseline) | Haiku | 3 rounds, 5 yr, no strategy notes | 14 | 2030s | **≈145** | **$2.93** (Haiku rates) |
| *(deleted; previous canonical, 5-yr)* | Sonnet | 3 rounds, 5 yr, strategy on, `--log-prompts`, per-power placeholder personas | 18 | 4479s | **≈249** | **$11.98** + $0.50 commentary |
| *(deleted; previous 10-yr canonical, serial)* | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, uniform baseline persona | 36 | 9434s | **≈262** | **$24.69** + commentary |
| *(deleted; parallel-fan-out Haiku measurement)* | Haiku | 3 rounds, 5 yr, strategy on, `--with-commentary`, uniform baseline | 17 | 588s | **≈35** | **$3.43** (Haiku rates) |
| *(deleted; previous canonical, 10-yr, parallel)* | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, `--with-commentary`, uniform baseline persona, all 2026-06-01 prompt improvements | 33 | 1873s | **≈57** | **$24.03** + commentary |
| *(deleted; per-power-adjacency canonical, 10-yr)* | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, `--with-commentary`, uniform baseline persona, + per-power adjacency block | 35 | 2043s | **≈58** | **$25.23** + commentary |
| *(deleted; full-revision canonical, 10-yr)* | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, `--with-commentary`, full prompt revision: full power-adjacency matrix + expanded tactics + succinct support/convoy rules | 36 | 1962s | **≈55** | **$24.31** + commentary |
| 2026-06-04.14.48.20 **(canonical, 10-yr, parallel)** | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, `--with-commentary`, aggression-rebalanced prompt (persona "playing to win" + "holding still is losing" + "stab to win") | 41 | 2043s | **≈50** | **$25.62** + commentary |

**Headline (serial regime):** Haiku is ≈3-4× faster than Sonnet *per
phase on simple workloads* (1 round, no strategy notes). On the
canonical workload (3 rounds × strategy notes, the default) the
per-phase advantage collapses to roughly parity because per-phase
call count dominates: Haiku doesn't make fewer calls than Sonnet, and
the strategy + 3-round combo is call-heavy. Cost is still ≈1/3
across the board.

**Parallel fan-out effect:** the deleted Haiku measurement row shows
≈35 s/phase on Haiku canonical workload, vs ≈145 s/phase on the same
model under the serial plain-vanilla baseline, a 4.2× per-phase
speedup. The current Sonnet 10-yr canonical (`2026-06-04.14.48.20`,
last row) lands at ≈50 s/phase parallel vs ≈262 s/phase on the earlier
serial Sonnet canonical, a 5.2× speedup, for a 34-minute wall-time
total across 41 phases.

---

## Canonical prompt-revision comparison

Four 10-yr canonicals: three Sonnet runs tracking two batches of prompt work,
plus a Haiku run on the final prompt for a model-capability snapshot. All at
identical configuration so the deltas isolate one variable at a time (single
game each, so read as directional, not statistically significant). Only the
Sonnet aggression-rebalance run (`2026-06-04.14.48.20`) is retained as a
committed run (the showcased canonical); the other three are one-off
measurements whose numbers are preserved here:

1. **`2026-06-04.01.23.15`** (per-power adjacency): per-power "your neighbors"
   row, original tactics.
2. **`2026-06-04.04.00.49`** (full revision): full power-adjacency matrix for
   every agent, expanded tactics list, succinct support rules, documented
   convoy orders (army-side `VIA`), explicit `bounce`/result-label definitions.
3. **`2026-06-04.14.48.20`** (aggression rebalance): persona shifted to
   "playing to win, not to survive," new lead tactic "Holding still is
   losing," "Stab to win" (vs "time your stabs"), demilitarized zones reframed
   as temporary tools.
4. **`2026-06-04.17.36.33`** (Haiku, same prompt): run 3's rebalanced prompt
   with all seven powers on Haiku 4.5 instead of Sonnet 4.6, a model swap at
   about one-third the cost.

| KPI (index Outcomes) | per-power adj (Son) | full revision (Son) | rebalance (Son) | same prompt (Haiku) |
|---|---:|---:|---:|---:|
| Negotiation messages | 914 | 1036 | 1034 | 981 |
| Messages to non-adjacent powers | 13.6% | 20.2% | 19% | 23% |
| Conditional bargaining | 46.4% | 50.4% | 55.2% | 31.7% |
| Questions asked | — | — | 21.1% | 48.8% |
| Betrayals | 4.6% | 2.3% | 4.5% | 0.5% |
| Hold rate | 59.2% | 57.5% | 49.4% | 48.1% |
| Support orders | 11.7% | 12.3% | 14.5% | 6.9% |
| Bounces | 73 | 74 | 88 | 83 |
| Dislodgements | 12 | 11 | 17 | 5 |
| Builds | — | — | 26 | 17 |
| Disbands | — | — | 11 | 6 |
| Convoy orders | 0.0% | 0.0% | 0.3% | 1.6% |
| Illegal orders | 4.4% | 2.2% | 3.1% | 11.0% |
| Adjacency errors | 4.4% | 2.2% | 3.1% | 10.8% |
| Phases played | 35 | 36 | 41 | 32 |

"Questions asked" = share of messages containing a `?`. "Builds"/"Disbands"
are cumulative counts across all winter adjustment phases (retreat-phase
removals are excluded; they show up under Dislodgements). All three were
added after runs 1 and 2 were retired, so only runs 3 and 4 (transcripts
still on disk) are recomputable; the run 1/2 cells are blank (`—`).

**Full revision (1 → 2):** illegal orders and adjacency errors halved (clearer
support/order rules), and cross-board diplomacy rose sharply (negotiation
volume +13%, messages to non-adjacent powers 13.6% → 20.2%), consistent with
giving every agent the full power-adjacency matrix to reason about third-party
borders. But it did not fix passivity: hold rate barely moved and convoys
stayed at zero.

**Aggression rebalance (2 → 3):** the passivity intervention took. Hold rate
fell under 50% for the first time (57.5% → 49.4%), betrayals roughly doubled
(2.3% → 4.5%), dislodgements rose +55% (11 → 17) and bounces +19%, conditional
bargaining climbed (quid pro quo 55.2%), the first convoys appeared, and the
game ran longer (41 phases, more retreats and builds). The only cost was a
small illegal-order uptick (2.2% → 3.1%, still well below the 4.4% baseline),
the expected price of more boundary-pushing moves. n=1, so a few more runs
would be needed to separate signal from variance, but the direction is clear.

**Sonnet vs Haiku, same prompt (3 → 4):** on the identical rebalanced prompt,
Haiku is comparably *active* (hold rate 48% vs 49%, similar message volume and
cross-board outreach), so the anti-passivity framing lands on the weaker model
too. The gap is *competence*, not activity: Haiku's illegal-order and
adjacency-error rates run ~3.5x higher (11% vs 3%), it coordinates far less
(support orders 7% vs 15%, dislodgements 5 vs 17), and its negotiation is
thinner (conditional bargaining 32% vs 55%) with betrayals almost never
executed (0.5% vs 4.5%), a wider talk-vs-action gap. One inversion stands out:
Haiku asks questions in nearly half its messages (48.8% vs Sonnet's 21.1%),
leaning on the partner to supply information Sonnet more often commits to a
plan about. More interrogation, thinner follow-through. The board stayed even
(top power at 6, no runaway) where Sonnet produced a clear leader, at $8 vs $25.

---

## Quality observations

### Sonnet (canonical model)

Produces tight 1-2 sentence strategy notes, opens negotiations with
concrete bilateral proposals, closes deals across rounds, and lets
dialogue visibly drive orders. A now-retired 10-yr Sonnet canonical played
10 game-years to S1911M and ended with Germany dominant at 8 SCs,
three powers tied at 6 (France, Italy, Russia), Austria at 5, England
stuck at 3 throughout, and Turkey eliminated at F1906M.
Conditional-trade language (`"if you / if I / in exchange / in
return"`) appears in **51.7%** of all messages, anti-leader containment
talk is matched by **26 actual moves into the dominant power's
supply centers** across the game, and revised-strategy commitments
align with actual orders to a degree never observed in Haiku runs.
F1901M France-to-Germany opens with *"Would you support A BUR into BEL
from RUH? In return, I'll support you into Denmark or stay clear of
your northern moves"*, and the deal locks in at round 2 with both
sides committing to specific supports. This is the kind of A2A
behavior the goal-2 deliverable wants the demo to make visible.

### Haiku (cheaper, fallback for experiments)

- **Verbose strategy notes** — 4–6 sentences, often re-stating prior context
  in markdown ("**F1903M Strategy:**"). Reasonable substance, but flatter
  and less quotable than Sonnet's.
- **Pulled toward mutual-defensive stalemates with the strategy notes on** (the
  current default). In the partial 5-year run (`20260529T151442Z`), every
  power's SC count stayed at 3–5 from F1901M through F1903M — basically
  nothing happened for ≈2.5 game years. The strategy notes seem to reinforce
  a "consolidate, don't antagonize" stance across the Haiku table.
- **Without the strategy notes, Haiku plays a noticeably more dynamic game** — the
  plain-vanilla 5-year baseline `20260529T191351Z` ended at
  `RUS 6 / AUS 5 / ENG 5 / FRA 4 / TUR 4 / GER 3 / ITA 3`, with real growth
  and contraction (Germany and Italy actually shrank). Useful negative
  finding: the verbose self-strategizing was hurting more than it helped.
  Note: with `--strategy` now promoted to default behavior (hardwired),
  reproducing the "off" condition requires invoking `run_game(enable_strategy=False)`
  programmatically rather than via the CLI. If Haiku experiments need this
  again, we'd add a `--no-strategy` flag back.
- Likely viable for the controlled experiments **if** persona prompts
  (axis B) override the default cautious behavior; needs empirical
  confirmation, which is what axis A's first run is for.

### Negotiation failure mode: globally-salient vs relationally-relevant threats

Observed in an early Haiku 5-yr run (uniform `BASELINE_PERSONA`,
adjacency table on). Inspecting France's messages to Germany across
the three negotiation rounds before F1901M shows a pattern worth
naming.

All three rounds repeat near-identical content: *"Russia's growth is
alarming, 4 centers, GAL, UKR, RUM, BOT all under their control. If
they push into the Balkans or Mediterranean next, the balance breaks.
Something to watch closely together."* Four things go wrong at once:

1. **Russia's 4 centers is Russia's starting position.** Russia is the
   only power that begins with 4 SCs (MOS, STP, WAR, SEV); the other
   six start with 3. After S1901M every power still has its starting
   count, since SCs can only change in Fall. France is framing the
   opening board as new growth.
2. **GAL, UKR, BOT are not supply centers.** Of the four locations
   France lists, only RUM is an SC, and it's contested (Austria's
   `A SER → RUM` bounced Russia's `F SEV → RUM`, so Russia controls
   neither). The other three are non-SC territories where having units
   gains zero centers. France conflates "has a unit on a tile" with
   "owns a center".
3. **Russia is geographically irrelevant to France in 1901.** France
   and Russia share no border anywhere; for Russia to threaten France
   directly, Russia would have to cross Germany, Austria, or Italy
   first. The locally-relevant powers for an F-to-G channel are
   England (shared sea border), Italy (Piedmont/TYS), and Burgundy
   itself (the F-G fault line). Russia is the worst candidate for an
   F-to-G coalition pitch in this position.
4. **Three rounds of identical content with no concrete ask.** No
   proposed coordinated move, no conditional offer, no "you do X and
   I'll do Y". Just repeated vague warnings. The simultaneous-then-
   sequential round structure exists so agents can probe, react, and
   close; France used all three rounds for the same opener.

(1) and (2) are factual errors the model could fix with closer
reading of the SC standings block. (3) and (4) are the more
interesting findings: the model anchored on **"biggest power on the
board"** (Russia, 4 SCs) and offered that as **"biggest power relevant
to this conversation"**, ignoring geographic distance and the
recipient's actual neighbors. This is a generic A2A failure mode
where agents default to globally-visible signals over relationally-
correct ones, and worth checking for in any setting with information
asymmetry and limited shared structure.

**Mitigation 1 (targets items 1-3, relational relevance):** the
negotiation user prompt now instructs each message to be specifically
useful to its recipient, focused on threats and opportunities involving
units and powers adjacent to *them*, not generic concerns about
distant powers the recipient cannot act on. **Confirmed on a follow-up
Haiku run:** France's F1901M messages to Germany shifted from three
rounds about Russia (geographically irrelevant, factually wrong) to
three rounds about Burgundy (the literal F-G fault line) plus France's
actual western moves (Spain, Portugal, Gascony). Zero Russia mentions,
zero false SC claims.

**Mitigation 2 (targets item 4, react-and-close across rounds):** the
round-tactic note in the same prompt now branches three ways. Round 1
is for opening threads and probing. Middle rounds (round 2 of 3, round
2-3 of 4, etc.) tell the agent to react to messages received last
round: refine or counter a proposal, ask a follow-up, or commit to a
concrete trade in the "I will move A to B if you move C to D" form;
do not restate prior-round content. The final round demands a
concrete commitment (specific move + expected counter-move) and again
forbids restating.

**Partially confirmed on a subsequent Haiku run:**

- *Round-to-round content variation worked broadly.* 22 of 24
  sender-to-recipient pairs at F1901M show under 10 characters of
  prefix overlap between round 1 and round 2 messages, i.e. they
  open with different content rather than copy-pasting the prior
  round.
- *Best-case channel is Turkey-to-Austria, all 3 rounds.* R1 sets the
  Serbia-Bulgaria line, R2 reacts with "Still partners? If Russia
  pushes south we may need to keep watch", R3 cites actual board
  development ("Russia's move into RUM changes the calculus") and
  proposes coordination. Conditional reasoning, follow-up questions,
  content evolving with the game state. This is what the nudge was
  asking for.
- *Many pairs went silent in round 3*, e.g. G-to-F sent rounds 1-2
  only, R-to-G only 1-2, several others similar. That matches the
  prompt's "commit, counter, or stay silent" instruction rather than
  filling the round with restated content.
- *France remains an outlier.* F-to-G shows 15-character prefix
  overlap across rounds (everyone else 0-8); content really is
  near-identical across all three rounds even though Germany's
  round-2 reply visibly reacted to France's round-1 Burgundy
  reference. This looks like an agent-level or persona-position
  effect rather than a prompt problem.
- *Conditional trade syntax is rare: 1 of 57 messages at F1901M*
  contains "if you / if I / in exchange / in return / provided that".
  Only Italy-to-Turkey R2 follows the worked-example form. Haiku is
  not generalizing the "X if Y" structure from one-line examples in
  the prompt at scale; the form appears when it appears as an
  emergent property of the reasoning, not because the example was
  given.

**Reading:** the nudge helps the median pair but does not eliminate the
worst-case restating, and does not produce conditional-trade
syntax at the rate the example implied. Two further moves are
plausible (neither pursued yet): (a) a stronger prompt that
explicitly forbids re-confirming a prior agreement in middle/final
rounds, and (b) testing whether the worst-case restating is specific
to the France position under uniform persona, by varying persona or
swapping models on France alone.

**Sonnet does not exhibit this anchoring** on a now-retired 10-yr
canonical: F1901M France-to-Germany opens directly with
a concrete bilateral Belgium-support proposal, no Russia mentions,
no globally-salient-but-locally-irrelevant content. The anchoring is
a Haiku-specific failure mode at the boundary of the model's
capability floor, consistent with the broader Haiku finding below.

### Haiku capability floor under hardened prompts

This is a clean negative finding from the goal-3 axis-A direction:
under prompts hardened specifically to eliminate format-compliance
confounds and force orders to execute the agent's own stated plan,
Haiku still does not play coherent Diplomacy at the level needed for
legible A2A interaction. Reported here as a documented capability
result so future axis-A work starts from "Haiku is the floor" rather
than "Haiku might be fine with better prompts".

**Setup.** Haiku 4.5, 5 game-years, 3 negotiation rounds, uniform
`BASELINE_PERSONA`, adjacency table on, with the following prompt
hardenings live (all committed in `ad21678` and prior):

- Strategy-call `max_tokens` raised 220 to 500 so format compliance
  is observable without truncation noise.
- Strategy-call instruction adds a STRICT FORMAT clause: plain prose,
  1-2 sentences, no markdown headers, no bold, no bullet lists, no
  `**Strategy:**` / `Acknowledgements:` sections.
- Revised-strategy instruction adds an internal-consistency reminder:
  each unit can have only one order; supports require the supporting
  unit to be adjacent to the destination province.
- Orders prompt now states explicitly: orders should execute the
  commitments named in the most recent revised strategy note; if a
  stated move turns out to be illegal, substitute an order that
  pursues the same objective rather than abandoning it; if a coalition
  action was committed in negotiation, orders should reflect it.

Baseline for comparison is an identical Haiku 5-yr run with the
pre-hardening strategy/orders prompts (same model, year count,
persona, and negotiation prompt). Transcripts were inspected but
not retained; the analysis is preserved here.

**What the hardening fixed cleanly.**

| Metric | Pre-hardening | Post-hardening |
|---|---:|---:|
| Revised notes with markdown headers | 65 / 70 | **0 / 70** |
| Revised notes with bullet lists | 13 / 70 | **0 / 70** |
| Revised notes truncated mid-sentence | 28 / 70 | **0 / 70** |
| Median sentences per revised note | 4-6 | **2** |
| Avg revised-note length (chars) | 843 | 648 |
| Illegal-order rate | 7.7% (23/297) | **4.4%** (13/298) |

F1902M strategy-to-orders alignment, spot-checked across all 7
powers, is essentially perfect post-hardening. Every revised
strategy maps cleanly to the orders submitted. Compare to the
pre-hardening baseline where Germany F1902M revised committed
"F BAL → DEN" and orders sent F BAL → BOT, England F1902M revised
committed "A CLY → NWY" and orders sent A CLY → LVP.

**What the hardening did not fix.**

| Metric | Pre-hardening | Post-hardening |
|---|---:|---:|
| Conditional-trade rate (`"if you / if I / in exchange / in return"`) | 14.4% (77/536) | 14.4% (76/527) |
| Hold-rate, average across powers | 65.1% | **70.2%** (higher) |
| Hold-rate, max single power | 84% (Turkey) | 85% (England) |

All 13 illegal orders in the post-hardening run are
**support-adjacency violations**, the same specific rule (a support
order requires the supporting unit to be adjacent to the destination
province). Examples: Austria `A VIE S A SER` repeated across S1903M,
S1904M, S1905M (Vienna is not adjacent to Serbia); England
`F EDI S F NTH - DEN` (Edinburgh not adjacent to Denmark); Germany
`F BAL S A SIL` (Baltic not adjacent to Silesia); Italy
`F ION S A VEN - TYR`; France `F LYO S F TYS - TUN`. The rule is in
`rules.md`, the adjacency table is in the cached system prefix, the
per-phase legal-moves list shows what each unit can legally do, and
the revised-strategy instruction now restates the rule explicitly.
Haiku still violates it.

**Interpretation.** The strategy-to-orders gap closed, but mostly by
Haiku committing to less. Every revised strategy at F1902M says some
form of *"I'm holding defensively this fall"* or *"consolidating my
position"*. The hardened prompt eliminated the "overpromise in
revised, under-deliver in orders" pattern by causing Haiku to under-
promise in revised. Aggressive coalition action vanished from the
revised strategies too. The behavioral equilibrium is seven powers
all writing "no expansion this turn, just solid defense".

This shows up in outcomes: the post-hardening run ended with
`FRA=7, ENG=5, RUS=5, TUR=5, AUS=4, GER=3, ITA=3`, more balanced
than the pre-hardening `RUS=8, ENG=5, TUR=5, AUS=4, FRA=4, ITA=4,
GER=2` Russia runaway. The balance is real, but the causal mechanism
is "everyone played passively" rather than "everyone played skillfully
against a dominant power". France's 7 came from peaceful expansion
into uncontested centers (Belgium, Portugal, Mid-Atlantic Ocean
area), not from outmaneuvering anyone.

**Implication for goal-3 axis A.** Under maximally hardened prompts
that eliminate format and internal-consistency confounds, Haiku still
exhibits:

1. A residual ~4% illegal-order rate, concentrated entirely on a
   single rule (support adjacency) that is present in four redundant
   places in the prompt.
2. A behavioral equilibrium of mutual passivity, where the
   negotiation channel discusses coalition action but revised
   strategies and orders both retreat to defensive holds.
3. A talk-vs-action gap that closes only because the *talk* gets
   smaller, not because *action* gets larger.

A now-retired Sonnet 10-yr canonical showed
four residual failure modes, three shared with Haiku at lower rates
and one Sonnet-specific:

- **Support-adjacency illegal orders.** Illegal rate is 3.8% rather
  than 4.4%, and the residual is concentrated entirely on support
  adjacency: France's `A BUR S A BEL - HOL` repeats 8 times across
  phases, Italy's `F EAS S F AEG - GRE` repeats 5 times, Germany's
  `F NTH S A DEN - SWE` repeats 3 times. Support adjacency is a
  generic reasoning failure on this task, not a Haiku-specific one,
  and is the highest-impact remaining issue. Roadmap entry
  "Surface legal supports in the per-phase view" proposes a
  precomputed-allowlist fix.
- **Hold rate averages 53% across powers** rather than 70%. Lower,
  but still high in absolute terms (Germany 48%, England 54%, France
  65%); Sonnet is not playing a tactically aggressive game either.
  Some of this is defensive holds and tactical garrison, some is
  passive equilibrium; current metric does not distinguish.
- **Home-SC parking.** Sonnet leaves units on its own home SCs at
  roughly 1.3-2.5 units per movement phase (Germany averages 2.05 of
  3 home SCs occupied per phase, Russia 2.45 of 4, England 1.85 of
  3, vs France's much-better 0.65). Parking is correct defense when
  a home SC is under attack and wasteful when it blocks a winter
  build. Current rules.md sentence does not qualify "unnecessarily";
  a useful refinement would be to surface, on Fall phases for powers
  that gained SCs that year, the specific home SCs that must be
  empty for Winter builds.
- **Sonnet-specific: preemptive `ORDERS:` block in revised strategy.**
  The strategy-to-orders gap is mostly closed (F1904M spot-check
  shows near-perfect alignment between revised strategy commitments
  and submitted orders), but 109 of 132 revised strategy notes
  append a preemptive `ORDERS:` block to the strategy prose despite
  the prompt explicitly forbidding it. 89 of those preemptive blocks
  match the actual orders submitted in the separate call that
  follows; 20 mismatch. The prohibition that works on Haiku does not
  hold on Sonnet. Pure transcript noise rather than agent-behavior
  bug; could be stripped at render time without changing any game
  logic.

The behavioral gap that **does** clearly separate Sonnet from Haiku
is on the negotiation-channel side: conditional-trade language at
51.7% rather than 14.4%, real territorial swings, Turkey eliminated
by F1906M, visible bilateral deals driving order coordination,
26 actual moves into the dominant power's SCs across the game vs the
Haiku run's 2.

The right axis-A experimental design therefore is **mixed tables**
(one Sonnet in an otherwise Haiku table, or vice versa) to measure
how much a single capable agent can change the equilibrium, rather
than continuing to debug Haiku-homogeneous play. The "Haiku might
be fine with better prompts" hypothesis is rejected on the evidence
here.

---

## Agent prompt: adjacency table

By default the cached system prefix includes the complete adjacency
table for the standard Diplomacy map, generated at runtime by
[`diplomacy_a2a/game/adjacency.py`](diplomacy_a2a/game/adjacency.py)
from Meta's `diplomacy` library. The table is the single source of
truth for support-legality verification (the dominant failure mode of
agents on this task) and a redundant ground truth for move legality
alongside the per-phase legal-moves list.

**Format.** One line per location: `` - `LOC` (type): neighbors ``. Type
is `water`, `coast`, `land`, `fleet` (for coast-specific entries like
`STP/NC`), or `army` (for the bare-province entries of multi-coast
provinces). Neighbors are uppercase, comma-separated. Sample:

```
- `ADR` (water): ALB, APU, ION, TRI, VEN
- `PAR` (land): BRE, BUR, GAS, PIC
- `BRE` (coast): ENG, GAS, MAO, PAR, PIC
- `STP` (army): FIN, LVN, MOS, NWY
- `STP/NC` (fleet): BAR, NWY
- `STP/SC` (fleet): BOT, FIN, LVN
```

**Generation.** `loc_abut` from the library handles all non-multi-coast
provinces directly. For multi-coast provinces (STP, SPA, BUL), the
bare-province `loc_abut` entry is `None` because the library models the
coasts as the canonical locations; the army-view adjacency is synthesized
with `m.abuts("A", prov, "-", dest)` over all candidate destinations so
land-only neighbors like STP-MOS are not missed (a synthesis-by-coast-union
would).

**Notation note.** `loc_abut` mixes uppercase (fleet-reachable) and
lowercase (army-only land border) entries. The table normalizes everything
to uppercase to stay scannable for smaller models; the rare
fleet-supports-via-land-only-adjacency cases (e.g., a fleet at ANK
attempting a support involving the SMY land border) get caught by the
adjudicator rather than disambiguated in the prompt.

**Token cost.** ~1,100 tokens added to the ~1,750-token rules digest. At
Sonnet's cached-prefix rate of $0.30 / M cache_read across roughly 900
calls per canonical game, the table adds about $0.30 of cost.

**Opting out.** The `--no-adjacency-table` CLI flag replaces the table
with a fallback note instructing agents to infer adjacency from the
legal-moves list, dialogue, and training data. The flag exists to
support controlled-variation experiments (axis-E: information
asymmetry) without changing other agent behavior.

**Worked example in the prompt.** A short support-legality walkthrough
is included immediately before the table (in the same `## Geography
and adjacency` section of [`rules.md`](diplomacy_a2a/game/rules.md)) so
agents see how to use the table on a concrete case, reducing the
chance smaller models ignore the resource.

---

## Agent prompt: supply-center visibility

The view rendered by [`game/view.py::render_for_power`](diplomacy_a2a/game/view.py)
contains a single `## Supply centers` block that enumerates, for every power,
who owns which centers. As of commit `86b3f83` (2026-05-29) the block also ends
with an explicit **`Unowned (N): ...`** line listing the still-neutral SCs:

```
## Supply centers
- AUSTRIA ← YOU (3): BUD, TRI, VIE
- ENGLAND (3): EDI, LON, LVP
- FRANCE  (3): BRE, MAR, PAR
- GERMANY (3): BER, KIE, MUN
- ITALY   (3): NAP, ROM, VEN
- RUSSIA  (4): MOS, SEV, STP, WAR
- TURKEY  (3): ANK, CON, SMY
- Unowned (12): BEL, BUL, DEN, GRE, HOL, NWY, POR, RUM, SER, SPA, SWE, TUN
```

Before that commit, neutrals were invisible — the agent had to either recall
the standard map's 12 neutral SCs from training data or infer them by
intersecting the legal-orders menu with general map knowledge. The new line
is computed from `state.game.map.scs` minus the union of all owned centers,
so it (a) self-shrinks as the game progresses (by F1903 maybe only 2–3
neutrals remain), (b) works unchanged on variant maps, and (c) costs ≈20
extra tokens per prompt.

**Where SC-value framing comes from.** The cached system prefix contains
`rules.md`, whose `## Goal` section names both the win condition and an
explicit growth directive:

> Be the first power to **control 18 supply centers** (out of 34 on the
> board). A solo victory ends the game. Anything less is a loss or a draw.
>
> Supply centers are the principal resource that matters most in
> Diplomacy: more centers means a larger army (Winter Adjustments
> builds one unit per excess center) and more political weight at
> the table. Failing to acquire centers leaves you weaker each year
> while rivals grow.

The `## Strategy / context for negotiation` section reinforces this:

> The supply-center count after Fall (especially Fall 1901, Fall 1902)
> signals who is winning and reshapes alliances.

Agents are explicitly told that SCs are the win condition, that 18 is
the solo threshold, that 34 exist, that the Fall SC count is the
politically charged number, that SC count mechanically determines army
size, and that failing to acquire centers leaves them weaker while
rivals grow. Per-power persona variations (axis B, eventually) can
encode further acquisitiveness or restraint on top of this baseline.

---

## Agent prompt: power adjacency

The cached system prefix includes a `## Power adjacency` block giving **every
agent the full standard-map adjacency matrix for all seven powers**, not just
its own row. The addressee's row is marked `(you)`:

```
## Power adjacency (starting borders between powers)
These are the powers whose home territories border each other at the
start of the game. Adjacency is not fixed for the whole game: as units
advance across the board and powers gain or lose territory, powers that
did not start next to each other can come into contact, and some
starting borders fall away. Treat this as the opening picture, then
update it from the current board.

How to use it: if a power is pressuring you, look up that attacker's
row to see which powers border it. Those powers can attack it too,
which forces it to split its forces and defend elsewhere, easing the
pressure on you. A power that borders neither you nor your attacker is
less able to help you militarily right now.

- AUSTRIA: GERMANY, ITALY, RUSSIA, TURKEY
- ENGLAND: FRANCE, GERMANY, RUSSIA
- FRANCE: ENGLAND, GERMANY, ITALY
- GERMANY: AUSTRIA, ENGLAND, FRANCE, ITALY, RUSSIA
- ITALY: AUSTRIA, FRANCE, GERMANY
- RUSSIA: AUSTRIA, ENGLAND, GERMANY, TURKEY
- TURKEY (you): AUSTRIA, RUSSIA
```

**Why the full matrix, not just the addressee's row.** Coalition-building
turns on *third-party* adjacency, not your own. When Turkey is harried by
Russia, the useful question is "who borders Russia?" (England, Germany,
Austria), because those are the powers that can open a second front on
Turkey's attacker; France and Italy border neither and are poor military
allies against Russia. A single-row view can only tell an agent its own
neighbors, which cannot answer that. The full matrix can. This targets the
canonical failure mode where Turkey, ground down by an Italy/Austria/Russia
coalition, sent zero messages across ten game-years to England, France, and
Germany. It is a structural cue, not a strategic instruction: the agent is
given the relational data, not told whom to ally with.

**Definition.** The matrix is the static `POWER_ADJACENCY` graph in
[`game/state.py`](diplomacy_a2a/game/state.py), formatted for the prompt by
`generate_power_adjacency_table` in
[`game/adjacency.py`](diplomacy_a2a/game/adjacency.py). It is the symmetric
start-of-game home-region graph (each power's row is mirrored in its neighbors'
rows), kept static rather than recomputed per turn. The prompt is explicit that
this is the opening picture and that real adjacency shifts as units advance and
territory changes hands, so the agent is told to update it from the current
board rather than treat it as fixed. Keeping the table itself static (rather
than a per-turn footprint computation) avoids the opening problem where nearly
every power reads as non-adjacent while units still sit in home centers behind
neutral buffers, and gives a stable shared reference. It lives in the cached
system prefix (served at
cache-read rates after the first write), gated on the same `--adjacency-table`
flag as the province table so the axis-E information-asymmetry experiment can
withhold both. Cost is ≈100 tokens, added once per power's cached prefix.

---

## Controlled-variation experiments

Goal 3 in the README is N-1-identical / 1-varied A/B comparisons across four
axes, replacing the original full persona grid. Each axis lands here as it
runs, with method + per-power results table + verdict.

### Axis A — model capability (one stronger model in a homogeneous table)

**Method:** 7 games, each with one Opus "champion" seat and one Haiku
"underdog" seat; the other five seats stay Sonnet (the field default). The
Opus and Haiku powers sit as far apart on the board as possible (opposite
corners) so the two test subjects never directly duel, and each one's result
reflects its model against the surrounding Sonnet field. Across the 7 games
every power serves as the Opus champion exactly once and the Haiku underdog
exactly once, following a single 5-cycle (England, Austria, France, Russia,
Italy, back to England) plus a Germany/Turkey swap:

| Game | Opus champion | Haiku underdog |
|------|---------------|----------------|
| 1 | England | Austria |
| 2 | Austria | France |
| 3 | France | Russia |
| 4 | Russia | Italy |
| 5 | Italy | England |
| 6 | Germany | Turkey |
| 7 | Turkey | Germany |

Because every power plays both Opus and Haiku across the set, the headline
signal is a within-power paired delta, `centers(power as Opus) - centers(power
as Haiku)`, which differences out each power's positional baseline without a
separate control game. 3 negotiation rounds per movement phase, strategy notes
on, 10 game-years each; same shape as the canonical configuration, so the only
things varying are the two upgraded/downgraded powers.

Each run is self-describing: the `run_started` transcript record stores
`power_models`, so analysis recovers which power was Opus or Haiku directly
from the transcript (the timestamp run-id need not encode the condition).

Invocation (per game; the field stays Sonnet because `--model` is omitted):
```bash
python -m diplomacy_a2a run \
  --power-model ENGLAND=claude-opus-4-8 \
  --power-model AUSTRIA=claude-haiku-4-5-20251001 \
  --category model-capability
```

**Status:** *Plumbing landed in commit `7358cdd` (run_game `power_clients`
+ `--power-model POWER=MODEL` CLI flag + model-aware cost estimator). Design
finalized to the 1-Opus / 1-Haiku / 5-Sonnet rotation above; first runs
pending.*

Results will land under `results/model-capability/` when complete.

### Axis B — personality trait (one aggressive / untruthful / backstabbing / crazy)

*Not yet implemented.*

### Axis C — memory depth (one short or long context)

*Not yet implemented.*

### Axis D — two-agent collusion (pre-game shared agreement)

*Not yet implemented.*

---

## Provider boundary: swapping Anthropic for another LLM

All LLM calls in the codebase go through a single `LLMClient` protocol
defined in [`diplomacy_a2a/llm/client.py`](diplomacy_a2a/llm/client.py).
Two implementations satisfy it. `AnthropicClient`
([`anthropic_client.py`](diplomacy_a2a/llm/anthropic_client.py)) is the
default and uses the official `anthropic` Python SDK plus prompt-caching
headers. `GatewayClient`
([`gateway_client.py`](diplomacy_a2a/llm/gateway_client.py)) speaks
OpenRouter's OpenAI-compatible API (via the `openai` SDK) for cheaper
non-Anthropic models. `make_client`
([`factory.py`](diplomacy_a2a/llm/factory.py)) routes by model id: a
`claude-*` id goes to Anthropic, anything else to the gateway.

The protocol exposes one method,
`chat(system, messages, max_tokens, temperature) -> ChatResult`, with
strict types, so a further implementation (a different gateway, a local
model) drops in mechanically as a new file behind the same protocol.
Anthropic stayed the v1 choice because of prompt caching, which serves
the rules + persona prefix at ≈10% of full input price after the first
write and is critical to the per-run budget. The Sonnet 5-year canonical
saves ≈22% from caching alone. A future provider that lacks comparable
caching would cost roughly that much more per game on equivalent rates.

### Candidate cheaper models (June 2026 snapshot)

If the goal is roughly-Sonnet play at a lower bill, the leading
alternatives, with Sonnet 4.6 ($3 / $15 per M input / output) as the
reference:

- **Gemini 3 Flash** (Google), about $0.50 / $3.00, roughly 5x cheaper.
  Major-lab reliability and the closest everyday quality to Sonnet of the
  cheap options.
- **DeepSeek V3.2 / V4-Flash**, about $0.14-0.28 / $0.28-0.42, roughly
  10-35x cheaper. Strong reasoning lineage; OpenAI-compatible API natively.
- **Qwen3 Coder / 3.x**, about $0.30 / $1.50, open-weight, strong
  instruction-following.
- **Kimi K2.6**, about $0.95 / $4.00, long context, open-weight.

Honest caveat: there is no public Diplomacy benchmark, so "as good at
Diplomacy" is an inference, not a measured fact. Sonnet leads the general
leaderboards, but its largest margin is on coding and the gap narrows on
reasoning, which is closer to what Diplomacy exercises. The right test is a
one-year A/B against Sonnet judged on the actual deliverable: negotiation
richness plus illegal-order rate. The latter matters because legal-order
instruction-following is already a documented weak spot (see the
surface-legal-supports roadmap entry), and a cheaper model could regress
there in a way that shows up directly in the transcript. Test cost is a few
dollars.

### Model playtest results: cheap to frontier (10-year self-play)

Measured comparison (2026-06-09): a full 10-year homogeneous self-play game per
model (one model drives all seven powers), columns ordered cheapest to priciest,
from DeepSeek up to a frontier Opus reference. Generated by
[`reference/compare_models.py`](reference/compare_models.py); the order and
message metrics mirror the dashboard, while N_eff and dropped-turns are
reference-only. Game-level rows are n=1, so rank on the Competence block (each
rate averages over hundreds of orders) and read Board and Negotiation as color.
Sonnet is the committed canonical run (`results/canonical/2026-06-04.14.48.20`);
DeepSeek, MiMo, Haiku, Gemini and Opus are research runs kept in gitignored
`scratch/`, so the table below is the preserved result. Gemini and MiMo are
reasoning models run with reasoning minimized (`effort: minimal`); the Claude
models (Opus/Sonnet/Haiku) run direct via the Anthropic key with extended
thinking off.

| Metric | deepseek/deepseek-v4-flash | xiaomi/mimo-v2.5 | claude-haiku-4-5 | google/gemini-3.5-flash | claude-sonnet-4-6 | claude-opus-4-8 |
|--------|----------------------------|------------------|------------------|-------------------------|-------------------|-----------------|
| **Cost & runtime** | | | | | | |
| Cost (USD) | $1.17 | $1.66 | $8.05 | $17.35 | $25.62 | $184.16 |
| Wall-clock (min) | 54.5 | 31.9 | 21.8 | 9.0 | 34.0 | 24.5 |
| Phases played | 36 | 36 | 32 | 34 | 41 | 39 |
| **Board** | | | | | | |
| N_eff (final) | 6.02 | 5.72 | 6.45 | 5.78 | 5.61 | 5.45 |
| Max SC (final) | 9 | 8 | 6 | 7 | 8 | 9 |
| Land turnover | 12 | 24 | 7 | 12 | 27 | 19 |
| **Competence** | | | | | | |
| Total orders | 626 | 634 | 563 | 641 | 640 | 654 |
| Illegal % | 7.0 | 6.0 | 11.0 | 2.8 | 3.1 | 3.7 |
| Adjacency % | 6.4 | 6.0 | 10.8 | 2.8 | 3.1 | 3.4 |
| Dropped turns % | 0.7 | 0.2 | 4.4 | 0.0 | 0.2 | 0.0 |
| Hold % | 59.4 | 48.4 | 48.1 | 53.0 | 49.4 | 33.2 |
| Support % | 7.5 | 13.6 | 6.9 | 20.1 | 14.5 | 34.3 |
| Support move % | 4.3 | 6.0 | 5.0 | 5.3 | 9.5 | 11.2 |
| Support hold % | 3.2 | 7.6 | 2.0 | 14.8 | 5.0 | 23.1 |
| Support eff % | 77.8 | 76.3 | 96.4 | 61.8 | 67.2 | 65.8 |
| Support bounced % | 14.8 | 15.8 | 0.0 | 29.4 | 27.9 | 26.0 |
| Support uncoord % | 7.4 | 7.9 | 3.6 | 8.8 | 4.9 | 8.2 |
| Convoy % | 2.6 | 0.5 | 1.6 | 1.6 | 0.3 | 2.0 |
| Self-bounces | 4 | 0 | 11 | 22 | 1 | 16 |
| **Negotiation** | | | | | | |
| Messages | 1359 | 1501 | 981 | 1378 | 1034 | 1309 |
| Bargaining % | 48.5 | 42.1 | 31.7 | 18.0 | 55.2 | 25.7 |
| Alliances % | 26.3 | 18.9 | 16.2 | 18.9 | 18.8 | 6.1 |
| Betrayals | 37 | 97 | 5 | 18 | 47 | 13 |

**Reading.**

- **Cost and speed:** six tiers, DeepSeek $1.17, MiMo $1.66, Haiku $8.05, Gemini
  $17.35, Sonnet $25.62, and Opus the frontier outlier at $184.16, about 7x
  Sonnet (above the ~5x its per-token rates suggest: ~79% of the bill is fresh
  input at $15/M. Opus's chattier negotiation (1309 vs 1034 messages) and ~2x
  longer strategy notes accumulate into a larger running context that is re-sent
  on every later call, inflating input across the game; output is only ~6% above
  Sonnet's, not the driver).
  Gemini is the fastest (9.0 min, reasoning minimized); DeepSeek the slowest
  (54.5 min: no gateway prompt caching, higher per-call latency, retries).
- **Competence (trustworthy):** Gemini is the cleanest budget-or-mid player
  (illegal 2.8%, 0 dropped), Sonnet next. Among the budget models, **MiMo edges
  DeepSeek**: lower illegal rate (6.0 vs 7.0%), far better coordination (Support
  13.6 vs 7.5%, near Sonnet), and fewer dropped turns (0.2 vs 0.7%). Haiku is
  weakest (illegal 11.0%, dropped 4.4%).
- **Opus (frontier reference):** the most coordinated and active player by a wide
  margin, Support 34.3% (more than double any other model), split heavily across
  offensive (move 11.2%) and defensive (hold 23.1%) support, and the lowest Hold
  rate (33.2%), so it constantly maneuvers rather than sitting. Clean (illegal
  3.7%, 0 dropped). Whether that coordination edge is *better play* needs a
  head-to-head, not self-play; here it just shows a distinctive, support-heavy
  style at the top of the price range.
- **Support breakdown (offensive vs defensive):** the Support % splits into
  move-supports (backing an attack) and hold-supports (backing a unit in place).
  Sonnet's coordination is the most offensive (move 9.5%); Gemini's high Support
  is mostly defensive (hold 14.8% vs move 5.3%), so it builds walls more than it
  backs attacks. Each move-support has one of three outcomes that partition it
  and sum to 100%: eff/successful (the attack landed), bounced (ordered but
  opposed or cut), or uncoordinated (backing a move that was never ordered).
  Successful runs 62-78%; Haiku's 96% with 0% bounced confirms its inert board,
  its supports were never contested. Uncoordinated, the self-coordination
  blunder, is a sparse 4-9% on tiny per-game counts, so n=1 noise here, useful
  only as a floor detector across many seeds.
- **Self-bounces (spatial coherence):** a legal move that bounces into a square
  your own side occupies, a self-standoff, so it never shows as illegal. It is
  orthogonal to the other competence metrics and exposes a different failure:
  Gemini (22) and Opus (16) self-bounce the most despite the cleanest illegal
  rates and the strongest coordination, so they follow the rules and coordinate
  but lose track of where their own units are; Sonnet (1) and MiMo (0) have the
  best spatial self-coherence. A frontier model self-bouncing 16 times (e.g.
  Turkey ordering `A SMY - ANK` into its own held `F ANK` in S1901M) is the kind
  of basic blunder a novice human avoids.
- **Board (color):** MiMo plays the most contested board of the cheap tier (Land
  turnover 24, vs DeepSeek 12 and Haiku 7, near Sonnet's 27); Haiku is the most
  static (turnover 7). Higher N_eff tends to track a quieter board.
- **Negotiation (color):** MiMo is the most aggressive negotiator of all five
  (97 betrayals and 1501 messages, both the most), which matters for the
  transcript deliverable. Sonnet bargains the most concretely (55%); Gemini talks
  but deals least (Bargaining 18%).
- **Verdict:** **MiMo-v2.5 is the best cheap value**, edging DeepSeek on play and
  negotiation richness for ~$0.50 more ($1.66). DeepSeek remains the rock-bottom
  cost pick ($1.17, functional if mid-tier). Gemini is the best play below
  Sonnet's price but expensive ($17.35, fast and cleanest on legality). Haiku is
  dominated (weakest competence at a middling $8.05). Kimi K2.6 stays out (~$20,
  visible verbosity plus truncation); Qwen3.5-Flash is cheaper still (~$0.5/10yr
  from a 1-year smoke) but mid-tier and uncoordinated, a pure cost play. **Opus**
  anchors the top of the quality/price range as the frontier reference: the most
  coordinated and active game in the set, but at $184 (~110x DeepSeek) it is not
  a value contender, it is the ceiling the cheap models are measured against.

### Opus vs Sonnet: play style (self-play deep-read)

A qualitative read of the two committed flagship games, the Sonnet `canonical`
run and the Opus `opus-reference` run, both 10-year self-play. This compares
STYLE, not skill: each game is one model driving all seven powers, so it cannot
rank the models (that is the model-capability rotation's job). It does surface a
consistent difference in how the two play.

**Same temperament, different execution.** Both games field articulate,
rule-literate, risk-averse negotiators who reason in explicit strength-math,
prefer turn-by-turn deals to named alliances, rarely betray, and verbally gang
up on the leader. The difference is whether that talk reaches the board.

| dimension | Sonnet (canonical) | Opus (reference) |
|-----------|--------------------|------------------|
| Coordination outcome | fragile: 14.5% support, 49% hold, 88 bounces, stalemate | coherent combined-arms: 34% support, lands 71% |
| After a failed attack | re-issues the same move 5-6 seasons (France A BUR-MUN six times) | pivots (Italy reroutes F ADR onto Trieste) |
| Anti-leader coalition | verbal only; England runs to 8-9 unchecked | actually pins France at 7 mid-game |
| Game shape | locked, grindy, no solo, leader uncatchable | decisive: England 4 to 9, Germany eliminated |
| Signature blunder | repeated illegal (impossible) supports, e.g. A PAR S A BUR-MUN three times | 13+ legal self-bounces in rotation chains |
| Negotiation flavor | "polite accountants", 55% bargaining | "shared order sheets", 26% bargaining, more precise |

**The self-bounce paradox.** Opus's signature flaw is the shadow of its
strength. It self-bounces 16 times (vs Sonnet's 1) because it juggles far more
units in active "no idle unit" rotation chains, and those chains jam against its
own occupancy (Turkey's F1906M double self-bounce mid-chain; England's recurring
home-waters pileup). Sonnet's near-spotless spatial record owes partly to a more
static game (more holds, fewer rotations, so less to misfire). The failure modes
mirror the temperaments: Opus blunders by ordering legal-but-self-defeating moves
while orchestrating a complex plan; Sonnet blunders by reaching for moves the map
forbids (illegal supports), then throwing the same doomed move at a wall for six
turns.

**Did Opus play "smarter"?** The read refines the question rather than answering
it. Opus shows more tactical execution (coordination that lands, real adaptation
after failure, a decisive outcome), the clearest sense in which it looks smarter,
but it also blunders more visibly, and because both games are self-play, Opus's
harder, more decisive game could reflect sharper opponents (a tougher table) as
much as a sharper model. The honest claim is about style: Opus is the more
executive, dynamic player (intent becomes board result); Sonnet the more static,
cautious one; and Opus's sophistication and its self-bounces are two faces of the
same ambition. The ranking itself waits on the model-capability rotation, where
the models meet on one board.

### One gateway key instead of three accounts

An LLM gateway (Vercel AI Gateway, OpenRouter) exposes Gemini, DeepSeek,
and others behind a single OpenAI-compatible key, account, and bill, at
list-ish prices: Vercel charges zero per-token markup (even with BYOK);
OpenRouter passes through list price plus a small credit-purchase fee
(~5.5%). This is implemented as `GatewayClient` against OpenRouter, with
the model chosen by string. The pinned candidate ids live in
`GATEWAY_MODELS` in [`config.py`](diplomacy_a2a/config.py)
(`deepseek/deepseek-v4-flash`, `google/gemini-3.5-flash`,
`moonshotai/kimi-k2.6`, `minimax/minimax-m3`). For the model axis that
reduces "swap providers" to "change the per-power model string."

Two caveats. Prompt caching: Anthropic always routes through the direct
`AnthropicClient`, so its ≈22% cache saving on Sonnet is fully preserved.
`GatewayClient` does not send `cache_control` breakpoints today, so its
`ChatResult` cache fields are 0; DeepSeek still caches automatically, while
Gemini and others run uncached through this path. The Anthropic Batch API
(the 50% sweep discount on the roadmap) is a separate async endpoint that
gateways generally do not expose; this is moot when the bulk sweeps run on
the cheap models, whose per-token price is already far below batched
Sonnet. Second, the gateway is opt-in: it reads its own `OPENROUTER_API_KEY`
and is reached only when a non-`claude-*` model id is selected, so the
"runs with only an Anthropic key" default holds.

---

## Output layout: top level vs `dashboard/`

Each run directory has two levels: source-of-truth artifacts
(`transcript.jsonl`, `prompts.jsonl`, `prompts.md`) at the top, and everything
derived (maps, `report.md`, HTML slideshow, `commentary.json`) under
`dashboard/`. The split exists so `rm -rf <run>/dashboard/` followed by
`render` is a safe, sub-second way to regenerate everything derived without
risking the irreplaceable LLM outputs at the top level. The HTML viewer's
internal links to top-level files use `../` prefixes; see `render_html_viewer`
in `transcripts.py` for the implementation.

---

## Re-running

LLM outputs are not byte-for-byte deterministic even at temperature 0,
so a rerun will produce *similar* dynamics, not identical transcripts.
Model IDs are pinned in `diplomacy_a2a/config.py` so reruns are
comparable across model releases.

The `render` subcommand is free (no LLM); `commentary` adds about $0.03
per phase of Sonnet calls (e.g. ≈$1 for the canonical's 33-phase game,
≈$0.50 for an 18-phase game); `--with-commentary` rolls game +
commentary + re-render into one command. A `--smoke` run (Haiku, 1 year, 1 round) costs pennies.

---

## Reliability: how API failures are handled

The runner classifies every Anthropic API failure into *fatal* (abort the
run, no retry) or *retryable* (exponential backoff). Logic lives in
[`anthropic_client.py`](diplomacy_a2a/llm/anthropic_client.py). The SDK's
built-in retries are **disabled** (`max_retries=0`) so our layer is the
only one and every failure is visible.

| Anthropic error | Category | Disposition |
|---|---|---|
| `AuthenticationError` (401) | `auth` | **Fatal** — "check `ANTHROPIC_API_KEY` in .env" |
| `PermissionDeniedError` with "credit" in message | `permission_or_credits` | **Fatal** — "add funds at console.anthropic.com" |
| `PermissionDeniedError` (other) | `permission_or_credits` | **Fatal** |
| `BadRequestError` (400) | `bad_request` | **Fatal** — likely oversized prompt or bad model id |
| `NotFoundError` (404) | `not_found` | **Fatal** |
| `UnprocessableEntityError` (422) | `unprocessable` | **Fatal** |
| `RateLimitError` (429) | `rate_limit` | Retry, honor `retry-after` header |
| `InternalServerError` (5xx) | `server_error` | Retry with exponential backoff |
| `APITimeoutError` | `timeout` | Retry |
| `APIConnectionError` | `network` | Retry |

Retry policy: up to **4 retries** by default (configurable via
`AnthropicClient(max_retries=N)`), exponential backoff capped at 30 s, or
the value of the `retry-after` header if present.

Every retry attempt and the final disposition are logged into the
transcript as `api_error` events with `{attempt, error_type, fatal,
category, message, model, status, power}`. The viewer ignores these
events; they're forensic-only. A quick way to summarize after a run:

```bash
python3 -c "
import json, collections
ev=[json.loads(l) for l in open('results/<run-id>/transcript.jsonl') if l.strip()]
errs=[e for e in ev if e['type']=='api_error']
print(collections.Counter((e['category'], e['fatal']) for e in errs))
"
```

When a fatal error is raised, `run_game` lets `RunnerError` propagate;
the CLI catches it and prints a friendly message before exiting 1. The
transcript will lack a `run_ended` event — that absence is itself the
signal of an incomplete run.

## Known issues & errata

- **Pre-`7358cdd` cost reports** for Haiku-only and mixed-model runs were
  inflated ≈3× because the estimator was hardcoded to Sonnet rates. Earlier
  reported costs in this file's table show both numbers where applicable.
- **Prompt caching may not be firing on Haiku 4.5.** The plain-vanilla
  baseline `20260529T191351Z` ran 2.23 M input tokens and the transcript
  recorded `cache_create = 0` and `cache_read = 0` for the entire run —
  i.e. zero cache savings. For comparison, the Sonnet canonical's
  `cache_read` is 260 K tokens (≈22% cost savings). Probable causes to
  investigate next: (a) Haiku's 2048-token cacheable-prefix minimum
  combined with how `system` is assembled, (b) a per-Haiku-version
  difference in `cache_control: ephemeral` handling, (c) something the
  model-aware refactor in `7358cdd` perturbed. Until resolved, treat
  the Haiku per-game cost as **≈$2.9 / 5-year game**, not ≈$1.0.
- **`20260529T151442Z`** ended at `S1905M round 1` because the API key ran
  out of credits mid-game (≈$0.07 unpaid balance at termination). The
  partial transcript still has 13 phases of usable data; the rendered viewer
  / `prompts.md` cover what was completed. Not pushed; remains in `results/`
  locally for forensic value.
- **Capturing run output via `| tail -N`** has bitten us twice now — the
  pipe masks the runner's exit code and hides any traceback in the
  discarded portion of stdout. For long runs, prefer `tee` or no pipe.

---

## How metrics are computed (for the scorer + KPI charts)

When the per-game scorer lands and the per-phase KPI charts go on the
slideshow:

- **PPSC** (final SC count): straight from `phase_resolved.centers` at the
  last resolved phase.
- **Survival rate**: `len(final_state.centers[p]) ≥ 1`.
- **Peak SC** (per power): `max(len(centers[p]))` across all
  `phase_resolved` events.
- **Year-to-N centers**: first phase where `len(centers[p]) ≥ N`.
- **Betrayals (heuristic, index-page Outcomes column)**: a "candidate
  betrayal" is a `(phase, speaker, province)` triple where the speaker
  sent a message containing a non-aggression promise keyword (`won't`,
  `will not`, `stay out`, `no interest in`, `respect`) plus a 3-letter
  ALL-CAPS token matching a province code, AND the speaker's adjudicated
  orders for that same phase include a move whose destination is that
  province. The triple is deduplicated so a promise repeated across
  negotiation rounds counts once. The percentage shown is
  `betrayals ÷ total negotiation messages` (10-yr Sonnet canonical:
  22/919 = 2.4%; 5-yr earlier example: 22/592 = 3.7%). Read this as an
  order-of-magnitude betrayal signal rather than an exact tally: a
  3-letter ALL-CAPS English word inside a "promise" sentence can fire
  the detector even when no real promise was made, and subtler
  promises that lack the keyword markers are missed entirely. A short
  stop-list (`IF`, `AND`, `BUT`, `THE`, `OUR`, `ALL`, …) filters the
  most common false-positive 3-letter tokens.
- **Offence score** (per-power cumulative line chart on the dashboard index,
  signed): rewards taking ground each movement phase. Every successful move earns
  **+2** for **dislodging an enemy** (taking a province it occupied, land or sea)
  or **+1** for **advancing into a vacant province** (a follow into a square the
  enemy merely vacated scores +1, not +2); separately, losing a supply center
  costs **-1** if you garrisoned it, **-2** if you left it undefended. Cumulative
  net per power. Because it credits maneuvering, not just captures, it is
  decoupled from the final standings: a power that probes and advances a lot can
  outscore the eventual winner (in the canonical game England wins on 8 centers
  with offence 13, while France and Italy maneuver more for offence 20 each).
- **Defence score** (per-power cumulative line chart, signed): scores units
  *under attack* each movement phase. A unit is attacked when an enemy ordered a
  move into its province. If it **held** (not dislodged): **+2** vs a supported
  attack, **+1** vs an unsupported one. If it was **dislodged**: **-2** on a
  supply center, **-1** elsewhere. Unattacked units score nothing. Cumulative net
  per power. Measures tactical unit survival, distinct from territory: a power can
  stay positive on defence while losing centers it never garrisoned (those losses
  fall on the offence score instead). The **+2 dislodge** line on offence mirrors
  the dislodge line here: an attack you land is the same event the defender
  survives or falls to.
- **Defence-vs-offence scatter** (dashboard index): one power-colored dot per
  nation, final offence (x) vs final defence (y), with dashed zero crosshairs
  marking the four offence/defence quadrants. Each nation's path through the
  plane over the game is overlaid as a translucent curve ending at its dot, so
  the journey is visible, not just the destination. Read it as play *style*: the
  x-axis is how hard a power pushed forward, the y-axis how its units fared under
  fire
  (e.g. in the canonical game France runs low on defence, a "glass cannon", while
  Russia runs highest, a "turtle"). All values are n=1 per game and, in
  self-play, reflect the seat's situation under one model, not cross-model skill.
- **Self-bounces** (index Outcomes, sub-row of Bounces; comparison table):
  count of move orders that bounced into a province the moving power occupies
  after resolution, i.e. a unit ordered into its own held square, or two of a
  power's units ordered into the same square so one bounces. Detected as a move
  whose unit is marked `bounce` in `results` and whose destination base is held
  by that same power in the post-resolution `units`. A legal order, so it never
  appears in `illegal %`; it isolates the self-inflicted slice of the raw bounce
  count and measures spatial self-coherence. Orthogonal to rule-following and
  coordination: cleanest-on-illegal models (Gemini, Opus) can still self-bounce
  the most.

Behavioral metrics (planned, axis B–D dependent):
- **Promise→action fidelity**: parse stated intentions in negotiation
  messages (e.g., "I'll move A BUL to GRE"), compare to the next phase's
  submitted orders.
- **Alliance duration**: consecutive phases of mutual support orders
  between a pair of powers.

---

## Roadmap

### Agent debugging portal

A user-or-developer-facing capability to ask any agent in a finished
run a post-hoc question. The agent's prompt context at the chosen phase
(system prefix, view, dialogue, strategy notes) is reconstructed from
the transcript, and the question is appended as a final user message.
Two question modes are envisioned:

- **Strategic / interpretive**: "What was your biggest mistake this
  game?", "Why did you honor your Scandinavian deal with England all
  five years?", "Who would you trust most going into S1906?"
- **Debugging / state-verification**: "Turkey, who do you think
  currently owns Denmark?", "Which powers do you believe are still
  allied with you?", "What is your current SC count?" The state mode
  is useful for verifying that an agent's internal model of the board
  matches reality, especially when axis E (information asymmetry) is
  in play.

**Implemented** as [`diplomacy_a2a/interview.py`](diplomacy_a2a/interview.py)
plus the `ask` subcommand:
`python -m diplomacy_a2a ask <run-dir> <POWER> "<question>"`. It rebuilds the
power's whole-game view (strategy notes, orders, adjudicated results, and
private dialogue) from the transcript, or only up to `--phase <SHORT_PHASE>`
for the what-did-you-know-then state-verification mode; `--model` lets a
different/stronger model answer than the one that played. The answer reuses
the same rules + persona system prompt the agent played with (via
`agent.rules_with_tables`), minus the order/message output instructions, so it
replies in prose grounded in its own recorded words. Cost is about $0.10-0.15
per whole-game question on Sonnet (a few cents with `--phase` or
`--no-dialogue`).

### LLM baseline knowledge probe

Before running multi-agent experiments, directly query each candidate
model (Haiku 4.5, Sonnet 4.6, Opus 4.7) about what it already knows
about Diplomacy, on three categories of question:

- **Rules and game structure**: phase order, win condition, adjudication
  mechanics, build/disband rules.
- **Strategies and tactics**: well-known openings (Lepanto, Western
  Triple), supports and convoys, the "stab" concept.
- **Province layout and adjacency**: which provinces border which, sea
  vs land coast, supply-center locations.

Knowing the baseline matters because controlled experiments need to
disentangle model differences from base-knowledge differences. If Opus
knows the map perfectly and Haiku only partially, an axis-A result risks
conflating "better strategic reasoning" with "more accurate memorized
map". Similarly, axis E (information asymmetry, hiding the SC tracker)
only meaningfully tests an agent's inference ability if we know the
model couldn't have memorized the hidden info from training data.

Implementation: a script that asks each model the same fixed question
set and scores accuracy. Cost is small (a few dollars across all three
models).

### Surface legal supports in the per-phase view

The per-power view currently lists each unit's legal moves but does
not list the supports each unit could legally issue. Agents have to
infer support legality from the adjacency table (a support order
requires the supporting unit to be adjacent to the destination
province). Both Sonnet and Haiku get this wrong at scale: in the
canonical 33-phase Sonnet run, all 26 illegal orders are
support-adjacency violations, and specific patterns repeat across
many phases (France's `A BUR S A BEL - HOL` was attempted and dropped
as illegal 8 times across the game). The adjacency information is in
the prompt four times (rules.md, adjacency table, per-phase
legal-moves list, hardened strategy-call instruction) and both models
still violate the support-adjacency rule at a steady rate.

The fix is to precompute legal supports per unit per phase and
surface them alongside the legal-moves list. The agent then
pattern-matches against an explicit allowlist rather than reasoning
about adjacency. Adjudication is unchanged; only the prompt content
shifts.

Implementation: extend the per-power view (in `game/state.py`) to
include, for each of the agent's units, the (sender, destination)
pairs the unit could legally support, computed via the same
`m.abuts()` library calls that compute move legality. Adds a few
hundred tokens per per-phase view but eliminates the most repeated
illegal-order pattern. No model changes needed; works for both Haiku
and Sonnet. Roughly 50-100 lines.

### In-game per-year reflection

After each fall (or each game-year), give each agent a small extra
call that asks it to write a one-or-two-sentence "lesson note": what
it did this year, what worked, what didn't, what it would do
differently. The note lands in the agent's strategy notes alongside the
existing initial / revised strategy entries, so it's visible on
subsequent turns' calls and feeds back into how the agent reasons
about the next year.

The point is to give each agent a chance to step out of per-phase
tactics and look at the multi-phase arc. Reflection-on-action prompts
are well-supported in the agent-systems literature (ReAct-style
agents, the Voyager Minecraft work, etc.) as a cheap way to nudge
agents toward better follow-through across turns. This may directly
help the talk-vs-action gap observed in the canonical: the
negotiation channel discusses coalition action but revised strategies
and orders both retreat to defensive holds. A yearly reflection that
names the gap to the agent itself ("I committed to pressuring
Germany but parked all my units; I should follow through next year")
could close it.

Scope kept small on purpose: in-game only, no cross-game lesson pool,
no curation step. The pooled-lessons-across-games version (a
separate research direction) has serious problems with experiment
isolation (axis A-E controlled comparisons break if agents carry
lessons across runs), prompt bloat (cached prefix grows every game),
false-lesson amplification (wrong takeaways propagate to all future
games), and quality control (who curates which lessons land in the
prompt). Tackle that only after the in-game version is validated.

Implementation: one new LLM call per power per game-year (~7 calls
× 10 years = 70 calls per canonical, modest cost). New
`Agent.reflect_on_year(state, ...)` method patterned on the existing
`state_strategy` / `revise_strategy` methods, with its own short
instruction. The note appends to `strategies_by_power[power]` as a
new kind alongside initial / revised so the existing strategy-history
formatter surfaces it on subsequent turns.

### Localize adjacency in the per-call view

The cached system prefix carries the complete adjacency table for
the standard map (~2.5K tokens covering all 76 provinces). Most of
that table is irrelevant to any single agent at any given moment.
For Turkey at S1901M, France's coast adjacencies are noise; for
England in F1908M, the Mediterranean coast detail is noise.

Localize by computing, per call, the subset of adjacencies within
two hops of the agent's current units (and current home centers),
and surface that subset in the per-call view. Keep the full table
out of the cached prefix, or keep it there as a fallback while the
local view carries the relevant slice. Either way the model sees a
much smaller, more focused geography block per call.

This is the same shape of fix as "Surface legal supports" above:
precompute and surface the relevant local subset rather than asking
the agent to derive it from a global table. The two could share
infrastructure.

Considered and rejected: per-nation unique system prompts (one
specialized prompt per power, possibly with hand-curated opening
theory). Three problems: (a) the seven agents currently share a
cached system prefix and therefore one cache entry, dropping the
cost of subsequent calls; seven different prefixes break that
sharing and inflate cost. (b) Goal-3 axis A / B / E experiments rely
on six baseline-identical agents plus one variant. Per-nation
prompts blur the baseline. (c) Specialized prompts inject strategic
bias (a France prompt that mentions the Western Triple makes France
pursue the Western Triple, which is prompt curation, not agent
reasoning). The localize-adjacency route captures the geography-load
benefit without these costs.

### Cross-game strategic-lesson pool

**Sequenced after the goal-3 axis A-E controlled experiments
complete.** Before that point this item would break experiment
isolation, because each game would depend on prior games' pooled
lessons rather than only on its configured axis variable. After the
experimental phase is closed, the system is free to evolve.

The mechanic: each game's per-year reflection notes (see "In-game
per-year reflection" above) are collected into a persistent
cross-game pool, with the most generalizable lessons surviving into
every subsequent game's cached system prefix. Over many games the
prefix accumulates a curated body of strategic knowledge that the
agents start with rather than rediscover. The agents play measurably
smarter on later games than on earlier ones, in a way attributable to
the pool rather than to model improvements.

The central design problem is **curation**, not collection. Without
a curation pipeline the pool degrades into a noisy mix of correct
takeaways, wrong takeaways, and run-specific lessons that don't
generalize. A workable pipeline looks roughly like:

- **Score**: a critic LLM call rates each reflection note on
  generality (does it apply only to this game's specific board, or
  to most games?), specificity (does it describe an action with a
  concrete antecedent?), and recurrence (do similar notes show up
  across many games and powers?).
- **Deduplicate**: embedding similarity collapses near-duplicate
  notes to a single representative.
- **Retain**: a hard cap (top N by score) bounds the pool's growth.
  Alternative or complementary: windowed retention (only lessons
  from the last K games) or weighted (lessons whose application
  improved subsequent outcomes get higher retention).
- **Propagate**: surviving lessons are formatted as a "Lessons from
  prior games" block in the cached system prefix.

A minimal first cut might be just score + dedup + top-20 retention,
hand-evaluated for a few cycles before automating the pipeline.

What this **doesn't** do is also worth being honest about:

- **It does not fix tactical reasoning.** The canonical's residual
  illegal-orders rate is concentrated entirely on support-adjacency
  violations, a tactical reasoning failure that a cross-game pool
  cannot address. Tactical fixes (localized adjacency in the
  per-call view, surface-legal-supports) remain orthogonal.
- **It does not stabilize cost.** Each game's cached prefix grows
  with the pool, eating into cache budget and context limits. A
  cap on pool size is required to keep cost bounded across
  arbitrarily many games.
- **It does not substitute for axis B (persona) experiments.** A
  curated lessons pool is not a personality; it's accumulated
  strategic knowledge that all agents share.

What it offers, if executed: a small system that **demonstrably
accumulates strategic knowledge across runs**. CICERO did not do
this; each of its games was a fresh start. A working cross-game
pool would be a distinctive demonstration of the curation-plus-
propagation engineering that real-world AI consulting work
increasingly involves (production agents that need to improve from
fielded data without operator intervention on every turn).

Implementation scope is genuinely a project, not a commit: maybe
600-1000 lines counting the critic, embedding store, retention
logic, and prefix integration. Add roughly one LLM call per
reflection note for scoring (so ~70 critic calls per game) plus a
one-off batch dedup pass after each game. Cost overhead is modest;
engineering overhead is the real cost.

### Batch API for sweep cost reduction

Anthropic's Message Batches API charges a flat 50% of the synchronous
rate for the same model, same prompts, and identical output quality.
It stacks with prompt caching, so the two discounts compound. The only
difference is execution: a batch is asynchronous (submit, poll, retrieve;
the SLA is "within 24h," usually much faster).

The discount applies to any request, so it lowers single-game cost too in
principle. In practice it is not worth using for a single interactive game:
a game is a long chain of small dependent steps (round 2 sees round 1's
incoming messages; phase N+1 depends on phase N's adjudication), so a
synchronous step can only batch the ~7 logically-simultaneous per-power
calls within one negotiation round / order step, and the async submit-poll
latency between those small steps would make one game painfully slow. Keep
the current synchronous threaded path (`_run_for_each_power` in
`runner.py`) for demo and iteration, where latency matters and dollars
do not.

The payoff is the unattended controlled-variation sweep (axes A-D, configs
x seeds), which is many *independent* games. There, batch across games
rather than within one: "round 1 negotiate for FRANCE" becomes one batch
of N requests across the N games in flight, not 7. Batch sizes get large,
the async latency is amortized across the whole grid, and the sweep's
dominant token cost drops by half with zero quality change and no second
provider. This is the lowest-risk cost lever available because it touches
neither the model nor the prompts.

Implementation: a batch execution mode for the sweep driver only. The
refactor inverts the run loop from "run one game to completion" to "advance
all games one step, collect that step's per-power calls into a batch,
submit, retrieve, apply results, repeat." The per-call prompt construction
and transcript bookkeeping are unchanged; what changes is the scheduler
around them, plus a thin batch path behind the `LLMClient` seam (submit /
poll / retrieve) alongside the existing synchronous `complete`. Worth doing
once the full axis grid is actually being run; for a handful of one-off
games the refactor does not pay for itself, and dropping to a cheaper model
saves faster. Composes with the provider-boundary work (a non-Anthropic
arm) and with prompt caching.
