# Model-capability axis:
### Four LLMs, from budget to frontier, play Diplomacy

This study compares 4 LLMs across the price/capability spectrum: mimo-v2.5
(budget), Claude Haiku 4.5 (small Claude), Claude Sonnet 4.6 (mid-tier), and
Claude Opus 4.8 (frontier). The price tiers are not parameter counts, and the two
decouple: MiMo is cheap but not small, a 311B-parameter open MoE, larger than the
genuinely small (~20B) Haiku yet a fraction of the Claude models' cost. This
investigation has two parts:

1. **Assessing self-play**: the same LLM plays against itself while driving all 7
   players in a game, one game per model. These games don't rank models, they
   instead characterize each LLM's playing styles which are quite different.
2. **LLM head-to-head**: the models meet on one board across seven counterbalanced
   ten-year games. Each game seats three test players, one Opus, one Haiku, and one
   MiMo, against a field of four Sonnets, with the test models spread apart for
   separation. Across the seven games Opus, Haiku, and MiMo each rotate through
   every nation once, which averages out board position and builds an LLM
   leaderboard for Diplomacy gameplay.

## The four models in self-play (style analysis)

**MiMo (S, budget): the talkative brawler.** The most talkative and most
aggressive negotiator of the four (~1500 messages, the most real betrayals),
and its betrayals are genuine and coercive, usually telegraphed: it reaffirms the
Trieste DMZ in spring 1901, then in F1902M tells Austria "let me have TRI
peacefully... if you refuse I'll take it by force" and seizes the home center.
Spatially it is the cleanest of the four (zero self-bounces). But its ceiling is
geometry: ~6% of its orders are illegal, and almost all of those are non-adjacent
support orders (a fleet "supporting" an attack it cannot reach), often the same
impossible order re-issued for many turns. It reflexively dogpiles the leader, so
its game is maximally contested and no one solos.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/mimo-reference/2026-06-09.03.23.24/dashboard/index.html)

**Haiku (budget runner-up): the agreeable diplomat.** The other budget candidate,
and the mirror image of MiMo's brawler. Haiku is the most *social* of the four
and the least *forceful*: the highest alliance language of any model (43% of
messages, double the next) and the most questions (39%), forever proposing
partnerships ("Turkey and Italy are natural partners... shall we coordinate?"),
yet near-zero betrayal (1.4%, against MiMo's 6.5%) and the lowest support rate
(8% vs 14%), so it offers friendship freely and almost never turns it into a hard
deal or a coordinated attack. It runs the most passive game of the four, the
highest hold rate (56%), the fewest dislodgements, and a single cut support all
game. And the coalition-talk never reaches the board: in spring 1902, with Russia
surging to seven centers, France warns the table "Russia is pulling away... let's
check its growth" while its only support that turn is its own grab for Burgundy in
the opposite direction. Russia is never checked, England quietly climbs to seven
and sits unchallenged for five straight years, and the board churns through 21
disbands without a single death or near-solo. That is the gap MiMo exploits: where
MiMo coerces ("if you refuse I'll take it by force") and seizes the center, Haiku
proposes a partnership and waits. The genial diplomat loses to the brawler.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/haiku-reference/2026-06-10.22.02.13/dashboard/index.html)

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
death across all four games). Negotiation reads like shared order sheets,
precise and transactional, betraying only when it announces why. Its signature
flaw is the shadow of its ambition: juggling many units in active rotation
chains, it self-bounces 16 times, ordering a unit into a square its own side
already holds.
Flagship game: [live dashboard](https://joehahn.github.io/diplomacy-A2A/results/opus-reference/2026-06-09.17.03.53/dashboard/index.html)

### What they share, and where they ladder

Three patterns recur across all four games, regardless of model family or price:

- **The containment reflex, and no solo.** Every model, every game, reflexively
  names the leader and tries to organize a coalition against it. It works well
  enough that none of the four games produces a solo winner; the leader is
  always dragged back to a no-solo finish. This looks induced by the shared
  persona/prompt as much as by the models.
- **A coordination-failure ladder.** The tier trio all try to coordinate (support
  orders) and fail in tiers that climb the competence stack. MiMo's supports are
  often **illegal** (it mis-models which provinces a fleet can reach). Sonnet's
  supports are legal but **bounce** (it cannot engineer the strength to break a
  wall). Opus's supports **land**, but it jams its own units (**self-bounce**). As
  capability rises, the failure moves from "doesn't model the geometry" to "models
  it but can't break a line" to "breaks lines but trips over its own ambition."
  Haiku falls off the bottom of the ladder: with the lowest support rate of all
  (8%) it mostly does not try, so its failure is absence rather than misfire.
- **The self-bounce paradox.** Counterintuitively the cheapest model is the
  spatially cleanest (MiMo, 0 self-bounces) and the frontier model the messiest
  (Opus, 16); Haiku, also low-ambition, jams itself just 4 times. Self-bounces
  track ambition and plan complexity (how many units you actively rotate), not raw
  capability; MiMo stays clean partly because it attempts less.

A longer Opus-vs-Sonnet read lives in [`REFERENCE.md`](../../REFERENCE.md) under
"Opus vs Sonnet: play style."

## Four LLMs head-to-head (the leaderboard)

Seven counterbalanced ten-year games run by
[`experiments/llm_axis.py`](../../experiments/llm_axis.py): three test models, Opus
(frontier), Haiku (small Claude), and MiMo (budget), each rotate through all seven
powers once, against a field of the mid-tier Sonnet on the other four seats.
Because every test model plays each power exactly once, board position is averaged
out and each is measured against the same Sonnet field. The cross-game plots below
are collected in the
**[rotation dashboard](https://joehahn.github.io/diplomacy-A2A/results/model-capability/dashboard/index.html)**
(derived from the seven transcripts by
[`experiments/model_capability/build_axis_dashboard.py`](../../experiments/model_capability/build_axis_dashboard.py)).

**On territory, a clear ranking.** Ten years is long enough for capability to
separate the field, and it does. Final supply centers per nation: Opus 6.6, Sonnet
4.9, MiMo 4.1, Haiku 3.7. Opus clears the 4.86 board average by nearly two centers
and leaves everyone behind, the mid-tier Sonnet sits right at average, and the two
budget models trail below it. This is the leaderboard the 3-year rotation could not
write, where every model had finished within a tenth of a center of average. The
trajectories show how it happens: the four climb out of the opening together and
stay tangled until about 1905, when Opus diverges upward while the rest plateau.
The long game is what converts cleaner execution into ground.

**On execution, the ladder mostly holds.** Order quality separates roughly as the
self-play games predicted, though not by price alone. Illegal-order rate splits the
Claude models from the budget pair: Sonnet 3.7% and Opus 4.8% against MiMo 8.5% and
Haiku 8.8%, the same geometry ceiling the cheap models hit in self-play. The
self-bounce paradox survives at scale, MiMo jams its own units zero times because
it barely coordinates, while the models that attempt more coordination jam more.
And coordination is where Opus pulls away: it orders supports on 35% of its moves,
against Sonnet's 14% (next-highest) and Haiku's 7%. That combined-arms ambition,
not cleaner basic orders, is what wins it the extra centers.

**On price and size, the frontiers come alive.** With territory now separated, the
cost and parameter frontiers (both flat at 3 years) acquire a slope. Final centers
climb with spend across the ~95x cost range, and rise with scale across more than
two orders of magnitude in parameters (Haiku ~20B to Opus ~2.7T), so at ten years
dollars and size both buy ground. Two wrinkles complicate the simple "more is
better" read. Haiku is a value-trap: it costs five times MiMo yet wins fewer
centers, so the genuinely small Claude is dominated by the larger-but-cheaper open
MoE on both axes. And cleanliness does not track price, Sonnet, not Opus, posts the
fewest mistakes; Opus trades some order-cleanliness back for the ambition errors
that come with coordinating far more.

The headline: ten years is the game length where the model-capability axis finally
writes itself in centers. Opus wins the board, the mid-tier holds the average, and
the two budget models trail, the smallest model (Haiku) last and the cheapest
(MiMo) the best value. Scale and spend both predict territory once the game is long
enough to turn execution into ground.

## Cost: the price spread these tiers represent

The headline cost of one 10-year self-play game per model:

| tier | model | 10-year self-play cost | input tokens | output tokens | wall time |
|------|-------|------------------------|--------------|---------------|-----------|
| S (budget) | xiaomi/mimo-v2.5 | $1.66 | 11.2M (uncached) | 334K | 32 min |
| S (alt) | Claude Haiku 4.5 | $7.30 | 10.3M (58% cached) | 453K | 32 min |
| M (mid) | Claude Sonnet 4.6 | $25.62 | 11.9M (48% cached) | 347K | 34 min |
| L (frontier) | Claude Opus 4.8 | $184.16 | 17.4M (45% cached) | 369K | 25 min |

Roughly a 110x cost spread from budget to frontier, driven by per-token rates,
not volume: all four games run a comparable number of LLM calls (~880) and
land within 2x on tokens and wall time. Cached input (the bracketed share
above) is billed at 10% of the full input rate. The budget runner-up, Claude
Haiku, lands in between, a Claude-family budget model at roughly 4x MiMo's cost
but a quarter of Sonnet's. Per-token rates and the full six-model
cost-and-competence comparison are in [`REFERENCE.md`](../../REFERENCE.md).

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

## Reproducing this study from the command line

Everything here regenerates from the repo. You need an Anthropic API key (and an
OpenRouter key for MiMo, which routes through the gateway) in `.env`, and an
active venv: `source .venv/bin/activate`. Costs per game are in the table above;
model IDs are pinned in [`config.py`](../../diplomacy_a2a/config.py).

**Self-play (one 10-year game per model, the style profiles).** Each writes to
`results/<category>/<timestamp>/` and auto-renders its own dashboard:

    python -m diplomacy_a2a run --model xiaomi/mimo-v2.5           --years 10 --rounds 3 --category mimo-reference
    python -m diplomacy_a2a run --model claude-haiku-4-5-20251001  --years 10 --rounds 3 --category haiku-reference
    python -m diplomacy_a2a run --model claude-sonnet-4-6          --years 10 --rounds 3 --category canonical
    python -m diplomacy_a2a run --model claude-opus-4-8            --years 10 --rounds 3 --category opus-reference

**Head-to-head rotation (seven 10-year games, ~$240, ~4 hours).** Opus, Haiku, and
MiMo rotate through all powers against a Sonnet field; the roster and balanced
rotation live in [`experiments/llm_axis.py`](../../experiments/llm_axis.py). It
runs sequentially and is resumable (a re-run skips games already finished), and
`caffeinate -i` keeps the Mac awake for the duration:

    caffeinate -i python experiments/llm_axis.py          # full sweep
    python experiments/llm_axis.py --dry-run              # print the 7 commands, run nothing
    python experiments/llm_axis.py --smoke                # one 1-year game to scratch/, to sanity-check

**Rebuild the rotation dashboard (the cross-game plots above).** No LLM calls,
sub-second; it globs `results/model-capability/*/transcript.jsonl`:

    python experiments/model_capability/build_axis_dashboard.py

**Re-render a single game's own dashboard** (maps, report, negotiation slideshow)
without replaying it (these per-game dashboards are gitignored, so regenerate
locally as needed):

    python -m diplomacy_a2a render results/<category>/<timestamp>
