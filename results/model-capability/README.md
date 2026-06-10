# Model-capability axis: three tee-shirt-sized LLMs play Diplomacy

This study compares three models across the price/capability spectrum on the same
game: a budget model (xiaomi/mimo-v2.5, **S**), a mid-tier model (Claude Sonnet
4.6, **M**), and a frontier model (Claude Opus 4.8, **L**). It has two halves:

1. **Self-play style profiles** (below): one 10-year game per model, that model
   driving all seven powers. These characterize *how* each model plays. They do
   NOT rank the models, self-play has no fixed-skill opponent, so they are style,
   not score.
2. **The head-to-head rotation** (further down): the three models meet on one
   board across seven counterbalanced games, where each rotates through every
   power. That is where the ranking lives.

Read the top half as personalities; read the bottom half as the leaderboard.

## Cost: the price spread these tiers represent

The headline cost of one 10-year self-play game per model:

| tier | model | 10-year self-play cost |
|------|-------|------------------------|
| S (budget) | xiaomi/mimo-v2.5 | $1.66 |
| M (mid) | Claude Sonnet 4.6 | $25.62 |
| L (frontier) | Claude Opus 4.8 | $184.16 |

Roughly a 110x spread from budget to frontier. For reference, the canonical
Sonnet game processes about 11.9M input tokens (about 48% cached and served at
10% of full price) and 347K output tokens across about 885 LLM calls, in about
34 minutes of wall time. Per-token rates and the full six-model cost-and-
competence comparison are in [`REFERENCE.md`](../../REFERENCE.md).

## The three models in self-play (style)

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
Flagship game: [mimo-reference](../mimo-reference/2026-06-09.03.23.24/dashboard/report.md)

**Sonnet (M, mid): the polite accountant.** Articulate, rule-literate, and
risk-averse; it reasons in explicit strength-math but rarely converts it. Its
coordination is conceptually correct yet mechanically fragile: plans bounce, the
board stalemates, and it re-issues the same failed move for five or six seasons
(France threw `A BUR - MUN` six times before Munich fell). Anti-leader coalitions
form in chat but never on the board, so the leader (England, 8-9 centers) is
never finished or checked. Tidy on defense, low on betrayal, and lighter on
ruthlessness than its own persona prescribes.
Flagship game: [canonical](../canonical/2026-06-04.14.48.20/dashboard/report.md)

**Opus (L, frontier): the staff officer.** Plays like seven disciplined staff
officers: peace-first openings, meticulously specified combined-arms that mostly
land (71% of its supported attacks succeed), genuine adaptation after a failed
attack, and a decisive game (England 4 to 9 centers, Germany eliminated, the only
death across all three games). Negotiation reads like shared order sheets,
precise and transactional, betraying only when it announces why. Its signature
flaw is the shadow of its ambition: juggling many units in active rotation
chains, it self-bounces 16 times, ordering a unit into a square its own side
already holds.
Flagship game: [opus-reference](../opus-reference/2026-06-09.17.03.53/dashboard/report.md)

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

## The head-to-head rotation (ranking)

*In progress.* Seven counterbalanced games (each model rotates through every
power, on opposite sides of the board, against a field of the mid-tier model),
run by [`experiments/llm_axis.py`](../../experiments/llm_axis.py). This section
will hold the per-model counterbalanced ranking, the supply-center and competence
plots, and outcome-vs-properties (cost, parameters) analysis once the games land.
