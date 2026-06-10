# Model-capability axis:
### Three T-shirt sized LLMs play Diplomacy

This study compares 3 LLMs across the price/capability spectrum using mimo-v2.5
(small budget LLM), Claude Sonnet 4.6 (medium mid-tier model), and Claude Opus 4.8
(large frontier LLM), and this investigation has two parts:

1. **Assessing self-play**: the same LLM plays against itself while driving all 7
   players in a game, three games for 3 LLMs. These games don't rank models, they
   instead characterize each LLM's playing styles which are quite different.
2. **LLM head-to-head**: the three models meet on one board across seven
   counterbalanced games. Each game pits one Opus player and one MiMo player
   against a field of 5 Sonnets, with Opus and MiMo seated on opposite sides of
   the board for maximum separation. Across the seven games Opus and MiMo each
   rotate through every nation once, which averages out board position and lets us
   build an LLM leaderboard for Diplomacy gameplay.

## The three models in self-play (style analysis)

**MiMo (S, budget): the talkative brawler.** The most talkative and most
aggressive negotiator of the three (~1500 messages, the most real betrayals),
and its betrayals are genuine and coercive, usually telegraphed: it reaffirms the
Trieste DMZ in spring 1901, then in F1902M tells Austria "let me have TRI
peacefully... if you refuse I'll take it by force" and seizes the home center.
Spatially it is the cleanest of the three (zero self-bounces). But its ceiling is
geometry: ~6% of its orders are illegal, and almost all of those are non-adjacent
support orders (a fleet "supporting" an attack it cannot reach), often the same
impossible order re-issued for many turns. It reflexively dogpiles the leader, so
its game is maximally contested and no one solos.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/mimo-reference/2026-06-09.03.23.24/dashboard/index.html)

**Sonnet (M, mid): the polite accountant.** Articulate, rule-literate, and
risk-averse; it reasons in explicit strength-math but rarely converts it. Its
coordination is conceptually correct yet mechanically fragile: plans bounce, the
board stalemates, and it re-issues the same failed move for five or six seasons
(France threw `A BUR - MUN` six times before Munich fell). Anti-leader coalitions
form in chat but never on the board, so the leader (England, 8-9 centers) is
never finished or checked. Tidy on defense, low on betrayal, and lighter on
ruthlessness than its own persona prescribes.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/canonical/2026-06-04.14.48.20/dashboard/index.html)

**Opus (L, frontier): the staff officer.** Plays like seven disciplined staff
officers: peace-first openings, meticulously specified combined-arms that mostly
land (71% of its supported attacks succeed), genuine adaptation after a failed
attack, and a decisive game (England 4 to 9 centers, Germany eliminated, the only
death across all three games). Negotiation reads like shared order sheets,
precise and transactional, betraying only when it announces why. Its signature
flaw is the shadow of its ambition: juggling many units in active rotation
chains, it self-bounces 16 times, ordering a unit into a square its own side
already holds.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/opus-reference/2026-06-09.17.03.53/dashboard/index.html)

### What the three share, and where they ladder

Three patterns recur across all three games, regardless of model family or price:

- **The containment reflex, and no solo.** Every model, every game, reflexively
  names the leader and tries to organize a coalition against it. It works well
  enough that none of the three games produces a solo winner; the leader is
  always dragged back to a no-solo finish. This looks induced by the shared
  persona/prompt as much as by the models.
- **A coordination-failure ladder.** All three try to coordinate (support
  orders), and they fail in tiers that climb the competence stack. MiMo's
  supports are often **illegal** (it mis-models which provinces a fleet can
  reach). Sonnet's supports are legal but **bounce** (it cannot engineer the
  strength to break a wall). Opus's supports **land**, but it jams its own units
  (**self-bounce**). As capability rises, the failure moves from "doesn't model
  the geometry" to "models it but can't break a line" to "breaks lines but trips
  over its own ambition."
- **The self-bounce paradox.** Counterintuitively the cheapest model is the
  spatially cleanest (MiMo, 0 self-bounces) and the frontier model the messiest
  (Opus, 16). Self-bounces track ambition and plan complexity (how many units you
  actively rotate), not raw capability; MiMo stays clean partly because it
  attempts less.

A longer Opus-vs-Sonnet read lives in [`REFERENCE.md`](../../REFERENCE.md) under
"Opus vs Sonnet: play style."

## Three LLMs head-to-head (the leaderboard)

Seven counterbalanced games run by
[`experiments/llm_axis.py`](../../experiments/llm_axis.py): Opus (frontier) and
MiMo (budget) each rotate through all seven powers once, on opposite sides of the
board, against a field of the mid-tier Sonnet. Because every power plays each test
role exactly once, board position is averaged out and each test model is measured
against the same Sonnet field rather than dueling the other test model. Games run
3 years; the rotation is seven games, so it is run short to keep the bill down.
The three cross-game plots below are collected in the
**[rotation dashboard](https://joehahn.github.io/diplomacy-A2A/results/model-capability/dashboard/index.html)**
(derived from the seven transcripts by
[`experiments/model_capability/build_axis_dashboard.py`](../../experiments/model_capability/build_axis_dashboard.py)).

**On territory, a near-tie.** Every model finishes within a tenth of a center of
the 4.86 board average (all 34 centers over 7 powers): Opus 4.86, Sonnet 4.86,
MiMo 4.71. Three years is long enough to carve up all 34 centers but too short for
any tier to convert capability into a territorial lead; the within-model spread
(3 to 7 centers) is the seat, not the model. The supply-center trajectories say
the same thing over time; all three climb out of the 3.14-center opening in
lockstep and tangle around 4.7 to 4.9. If there is a leaderboard at this game
length, it is not written in centers.

**On execution, the ladder returns.** Where the models separate is order quality,
and they separate in exactly the order the self-play games predicted. Illegal-order
rate ranks cleanly by price: Opus 1.7%, Sonnet 2.5%, MiMo 5.5%, the budget model
roughly tripling the frontier's rate. This is the same geometry ceiling MiMo hits
in self-play, where non-adjacent supports are its signature error. Self-bounces
echo the self-play paradox too: MiMo never jams its own units (zero) because it
attempts the least coordination, while Opus self-bounces most per order, tripped up
by the ambition of juggling many units in rotation. (Move-support success is
noisier; only 13 to 16 legal move-supports each for Opus and MiMo across 3 years,
so read that panel as indicative, not decisive.)

The headline: at this game length the three models are nearly indistinguishable on
the scoreboard but clearly tiered on how cleanly they execute. Turning the
execution gap into a center gap would take a longer rotation.

## Cost: the price spread these tiers represent

The headline cost of one 10-year self-play game per model:

| tier | model | 10-year self-play cost | input tokens | output tokens | wall time |
|------|-------|------------------------|--------------|---------------|-----------|
| S (budget) | xiaomi/mimo-v2.5 | $1.66 | 11.2M (uncached) | 334K | 32 min |
| M (mid) | Claude Sonnet 4.6 | $25.62 | 11.9M (48% cached) | 347K | 34 min |
| L (frontier) | Claude Opus 4.8 | $184.16 | 17.4M (45% cached) | 369K | 25 min |

Roughly a 110x cost spread from budget to frontier, driven by per-token rates,
not volume: all three games run a comparable number of LLM calls (~880) and
land within 2x on tokens and wall time. Cached input (the bracketed share
above) is billed at 10% of the full input rate. Per-token rates and the full
six-model cost-and-competence comparison are in [`REFERENCE.md`](../../REFERENCE.md).

Where those tokens go, using the canonical Sonnet game (885 calls, 11.9M
input + 347K output) as the budget. Every call is one of three kinds, and the three
account for the whole budget; there is no other token sink.

| call type | calls | input (prompt + context) | output | share of all tokens |
|-----------|-------|--------------------------|--------|---------------------|
| negotiation | 420 | 5.6M | 243K | 48% |
| strategy | 280 | 3.8M | 37K | 31% |
| moves | 185 | 2.5M | 68K | 21% |
| **total** | **885** | **11.9M** | **347K** | **100%** |

Two things stand out. There is no separate "prompt" line because the prompt
*is* the input side of every call: about 97% of all tokens are input (the board
state, rules, persona, and running history re-sent on each call) and only ~3%
are model output. And negotiation is the single largest consumer at ~48%, which
fits the project's premise that the dialogue, not the move, is the deliverable.
