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
| 20260528T214253Z *(deleted; previous canonical)* | Sonnet | 3 rounds, 2 yr, strategy log, `--log-prompts` | 7 | 1713s | **≈245** | $3.20 |
| 20260528T213153Z (smoke) | Haiku | 1 round, 1 yr, strategy log | 3 | 214s | **≈71** | $0.85 *(Sonnet-inflated; actual ≈ $0.28)* |
| 20260527T132540Z (smoke) | Haiku | 1 round, 1 yr | 3 | 180s | **≈60** | $0.46 *(actual ≈ $0.15)* |
| 20260529T151442Z *(partial, credit-out)* | Haiku | 3 rounds, 5 yr, strategy log, `--log-prompts-years 5` | 13 of ≈17 | ≈3300s | **≈252** | – |
| 20260529T191351Z (plain-vanilla baseline) | Haiku | 3 rounds, 5 yr, no strategy log | 14 | 2030s | **≈145** | **$2.93** (Haiku rates) |
| *(deleted; previous canonical, 5-yr)* | Sonnet | 3 rounds, 5 yr, strategy on, `--log-prompts`, per-power placeholder personas | 18 | 4479s | **≈249** | **$11.98** + $0.50 commentary |
| *(deleted; previous 10-yr canonical, serial)* | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, uniform baseline persona | 36 | 9434s | **≈262** | **$24.69** + commentary |
| *(deleted; parallel-fan-out Haiku measurement)* | Haiku | 3 rounds, 5 yr, strategy on, `--with-commentary`, uniform baseline | 17 | 588s | **≈35** | **$3.43** (Haiku rates) |
| 20260601T214429Z **(canonical, 10-yr, parallel)** | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, `--with-commentary`, uniform baseline persona, all 2026-06-01 prompt improvements | 33 | 1873s | **≈57** | **$24.03** + commentary |

**Headline (serial regime):** Haiku is ≈3-4× faster than Sonnet *per
phase on simple workloads* (1 round, no strategy log). On the
canonical workload (3 rounds × strategy log, the default) the
per-phase advantage collapses to roughly parity because per-phase
call count dominates: Haiku doesn't make fewer calls than Sonnet, and
the strategy + 3-round combo is call-heavy. Cost is still ≈1/3
across the board.

**Parallel fan-out effect:** the deleted Haiku measurement row shows
≈35 s/phase on Haiku canonical workload, vs ≈145 s/phase on the same
model under the serial plain-vanilla baseline, a 4.2× per-phase
speedup. The current Sonnet 10-yr canonical (`20260601T214429Z`, last
row) lands at ≈57 s/phase parallel vs ≈262 s/phase on the previous
serial Sonnet canonical, a 4.6× speedup, for a 31-minute wall-time
total across 33 phases.

---

## Quality observations

### Sonnet (canonical model)

Produces tight 1-2 sentence strategy notes, opens negotiations with
concrete bilateral proposals, closes deals across rounds, and lets
dialogue visibly drive orders. The current canonical
(`20260601T214429Z`,
`python -m diplomacy_a2a run --log-prompts --with-commentary`) played
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
- **Pulled toward mutual-defensive stalemates with the strategy log on** (the
  current default). In the partial 5-year run (`20260529T151442Z`), every
  power's SC count stayed at 3–5 from F1901M through F1903M — basically
  nothing happened for ≈2.5 game years. The strategy log seems to reinforce
  a "consolidate, don't antagonize" stance across the Haiku table.
- **Without the strategy log, Haiku plays a noticeably more dynamic game** — the
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

**Sonnet does not exhibit this anchoring** on the current canonical
(`20260601T214429Z`): F1901M France-to-Germany opens directly with
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

The committed Sonnet 10-yr canonical (`20260601T214429Z`) shows
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

The per-power view ([`game/view.py::render_for_power`](diplomacy_a2a/game/view.py))
includes a `## Power adjacency` block naming which other powers border the
addressee and which do not:

```
## Power adjacency (standard-map home regions)
- Adjacent (your natural neighbors): AUSTRIA, RUSSIA
- Non-adjacent (no shared border, reachable for distant diplomacy): ENGLAND, FRANCE, GERMANY, ITALY
```

The non-adjacent list is the diplomatically interesting half: those are the
powers an agent can court for a distant second front without an immediate
border threat. It targets the canonical failure mode where Turkey, eliminated
by an Italy/Austria/Russia coalition, sent zero messages across ten game-years
to England, France, and Germany, the exact powers who could have opened a
second front on its attackers. This is a structural cue, not a strategic
instruction: the agent is told the relational category exists, not to act on
it.

**Definition.** The block draws from the static `POWER_ADJACENCY` graph in
[`game/state.py`](diplomacy_a2a/game/state.py), the standard-map home-region
adjacency of the seven powers (symmetric; each power's row is mirrored in its
neighbors' rows):

| Power | Adjacent (natural neighbors) |
|---|---|
| Austria | Germany, Italy, Russia, Turkey |
| England | France, Germany, Russia |
| France | England, Germany, Italy |
| Germany | Austria, England, France, Italy, Russia |
| Italy | Austria, France, Germany |
| Russia | Austria, England, Germany, Turkey |
| Turkey | Austria, Russia |

The graph is static rather than recomputed from current unit positions: it
gives each agent a stable read on its structural rivals and its distant
courtship targets that holds all game, and it sidesteps the opening problem
where a per-turn footprint computation shows nearly every power as
non-adjacent (home centers sit behind neutral buffers until units advance into
contact). Cost is ≈30 tokens per per-call view.

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
separate control game. 3 negotiation rounds per movement phase, strategy log
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
The only v1 implementation is `AnthropicClient`
([`anthropic_client.py`](diplomacy_a2a/llm/anthropic_client.py)), which
uses the official `anthropic` Python SDK plus prompt-caching headers.

Adding a second provider (OpenAI, Gemini, a LiteLLM wrapper, etc.) is
intended to be a new file behind the same protocol, not a refactor. The
protocol exposes one method, `chat(system, messages, tools) -> response`,
with strict types, so a second implementation drops in mechanically.
Anthropic stayed the v1 choice because of prompt caching, which serves
the rules + persona prefix at ≈10% of full input price after the first
write and is critical to the per-run budget. The Sonnet 5-year canonical
saves ≈22% from caching alone. A future provider that lacks comparable
caching would cost roughly that much more per game on equivalent rates.

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
- **Sum-of-Squares share** (per phase, per power): `len(centers[p])²` ÷
  `Σ len(centers[p])²` over survivors. Eliminated powers contribute 0.
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

Implementation: a new `interview.py` module plus an `ask` subcommand,
roughly 80 lines total. Cost is about $0.01-0.03 per question on Sonnet.

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
differently. The note lands in the agent's strategy log alongside the
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
