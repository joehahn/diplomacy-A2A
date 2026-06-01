# diplomacy-A2A

![A Diplomacy board mid-game with pieces deployed across Europe](assets/diplomacy-board.jpg)

<sub>*A Diplomacy board mid-game: pieces from all seven powers deployed across
the European map. Gameboard photo from
[cardboardrepublic.com](https://www.cardboardrepublic.com/classics/risk-vs-diplomacy).*</sub>

**Diplomacy** is a 7-player strategy game set in pre-WWI Europe, where each
player controls one of the Great Powers (Austria, England, France, Germany,
Italy, Russia, Turkey) that are competing for supply centers that are
distributed across the map. No dice are used in Diplomacy, which means that
each nation's armies and navies advance or retreat deterministically per
players' orders. Every turn unfolds in parallel rather than in sequence: all seven players
negotiate simultaneously, write their orders in secret, and the orders are
then adjudicated as a single batch with no turn order.
What makes the game distinctive is that those negotiations are
unenforceable: any deal can be broken, betrayal is expected, and most
games are decided more by what was promised or lied about in private
than pure tactical cleverness.

This project replaces those seven human players with **seven Claude-powered
AI agents**. The agents negotiate privately each turn, choose their military
orders, and outcomes are adjudicated by simple rules that amount to
"the larger force prevails". Each game produces a full transcript of who
said what to whom, who honored deals, and who betrayed. The artifact that
matters here is the **negotiation transcript**, and not which agent wins,
because the transcript records the part of AI agent behavior that a benchmark
score cannot show: how each agent reasoned about who to trust, what to
promise, and when to honor or break a deal. The gap between what an agent
says in private and what it actually does on the board is visible to this
project's user at every turn.

This project is a successor to
[CICERO](https://www.science.org/doi/10.1126/science.ade9097), the 2022
Meta AI system that paired a fine-tuned language model with a separate
strategic-reasoning module to achieve human-level play on online Diplomacy.
CICERO controlled one of the seven powers in anonymous games on
webDiplomacy.net, while six humans controlled the others. But this effort
drops the strategic-reasoning module in favor of letting Agent-to-Agent
(A2A) communication manage all negotiations, with all decisions made by a
well-prompted frontier LLM, and with all players represented by AI agents.

## Visual dive into a representative game

You are invited to explore our **[canonical game](https://joehahn.github.io/diplomacy-A2A/results/20260531T202425Z/dashboard/index.html)**,
which uses Sonnet to power seven AI agents across 10 game-years. A game
year has five phases (Spring Movement & Retreats, Fall Movement &
Retreats, Winter Adjustments), so the canonical contains 20 movement
phases over those 10 years, with 3 rounds of inter-agent communication
before each movement. That dashboard shows the turn-by-turn movements of every army and
navy unit, full transcripts of the agent-to-agent (A2A) communications that
precede each turn, each agent's self-authored strategy notes, and an
LLM-generated summary of the gameplay that describes which nations used
A2A negotiations to advance their goals, which agents fumbled translating
negotiations into success, and who backstabbed whom.

## Project goals & deliverables

1. **Built with Claude Code, but reproducible with just an Anthropic key.**
   The project is *developed* using Claude Code, yet it *runs* on nothing more
   than the [Anthropic SDK](https://docs.anthropic.com/en/api/client-sdks)
   and an API key — Claude Code is the development harness, not a runtime
   dependency. Anyone can clone this, drop in their key, and rebuild or
   re-run the simulation.

2. **Highlight agent-to-agent interactions that move each other.** The point is
   not just that agents *send* messages, but that they *influence* one another —
   proposing, reacting across rounds, honoring or betraying deals — and that
   those interactions visibly drive how the game evolves. The negotiation
   transcript and the turn-by-turn dashboard are the deliverables that
   expose how effective those agents are at influencing each other, not
   whether any particular agent wins.

3. **Quantify what helps an AI agent succeed when it is competing against other agents in an A2A universe.** *(Under active development.)*
   Controlled A/B experiments where six agents are identical and one differs
   along a single axis: model capability (one Sonnet among Haikus, or one Opus
   among Sonnets), memory depth (one agent given more or less past-turn
   context), personality trait (one aggressive / untruthful / backstabbing
   agent at an otherwise neutral table), pre-game collusion (two agents
   share a private agreement to coordinate prior to game start), or
   information asymmetry (one agent has parts of its prompt hidden, such as
   the current supply-center ownership tracker, forcing it to infer
   standings from unit positions and dialogue alone). A planned deliverable
   from these experiments is a chart of agent success versus LLM spend,
   making the cost-benefit shape of each axis explicit.

## Real-world A2A analogies (placeholder)

Diplomacy is the testbed for these experiments, but the same structure
(many private parties, no central enforcement, every promise breakable)
shows up in real-world domains where AI agents are increasingly deployed
competitively. Candidate analogies under consideration for framing the
findings:

- **Programmatic advertising auctions** (real-time bidding): hundreds
  of thousands of bidder agents competing in sub-100 ms windows for the
  same ad impression; strategy is adversarial and payoffs are zero-sum
  within an auction.
- **M&A and procurement negotiations**: multi-round, multi-party,
  information-asymmetric, with side deals and coalitions that shift
  between rounds. Exclusivity periods get violated, NDAs get leaked,
  last-minute counter-bids appear.
- **High-frequency trading and market-making**: trading agents
  competing for execution priority and information edge against a
  shared, partially-visible order book.
- **Multi-party trade and climate negotiations**: the direct
  geopolitical analog of the testbed. Alliances shift between rounds,
  public statements often diverge from private positions, and
  enforcement is weak to nonexistent.
- **Cybersecurity red-team / blue-team agents**: opposing automated
  adversaries that must model each other's strategy and adapt in real
  time, on the same network or the same model.

Information asymmetry is the structural feature these domains share:
bidders never see opponents' reserves, M&A parties never see walk-away
prices, traders never see opponents' positions.

## Setup

This project requires Python 3.10+ (developed on 3.12) and an Anthropic API key.

```bash
git clone <this repo>
cd diplomacy-A2A
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your key into .env
```

## Game execution

The CLI does three things: it runs a game and stores game history as a
transcript (`run`), it renders the gameplay dashboard from a game transcript
(`render`), and it adds LLM-composed strategic commentary to that dashboard
(`commentary`).

```bash
# Execute default game (is Sonnet-powered, lasts 10 years, w/ 3 negotiation rounds per movement phase)
python -m diplomacy_a2a run

# Execute canonical game (10 yrs of gameplay + 1st-year dump of all agents' prompts & responses + LLM commentary)
python -m diplomacy_a2a run --log-prompts --with-commentary

# End-to-end verification using lower-cost Haiku for 1 year and 1 negotiation round
python -m diplomacy_a2a run --smoke

# all agents use stronger LLM
python -m diplomacy_a2a run --model claude-opus-4-7

# per-power model override (only Turkey uses Opus LLM)
python -m diplomacy_a2a run --power-model TURKEY=claude-opus-4-7

# per-power memory-depth override (Turkey context preserves past 5 movements)
python -m diplomacy_a2a run --power-memory TURKEY=5

# Render a finished game, this step does not use any LLM
python -m diplomacy_a2a render results/20260531T202425Z/

# Add or refresh LLM commentary on a finished run, then render
python -m diplomacy_a2a render results/20260531T202425Z/ --with-commentary

# Generate commentary only, no render (useful in scripts)
python -m diplomacy_a2a commentary results/20260531T202425Z/

python -m diplomacy_a2a --help                # subcommand list
python -m diplomacy_a2a run --help            # game-execution options
python -m diplomacy_a2a render --help         # render + commentary options
```

Artifacts (transcript, maps, dashboard, report) land under `results/<run-id>/`.
The transcript is the canonical artifact; every renderer derives from it.

### Options

The flags below let you swap the LLM (`--model`), tune game length and
negotiation depth (`--years`, `--rounds`), strengthen or weaken individual
agents (`--power-model`, `--power-memory`), and control output
(`--log-prompts`, `--with-commentary`).

| Flag | Default | What it does |
|---|---|---|
| `--model MODEL` | `claude-sonnet-4-6` | Anthropic model id used as the default for every power. Sonnet is the canonical game's workhorse; `claude-opus-4-7` is the stronger and more expensive AI while `claude-haiku-4-5-20251001` is less. |
| `--years N` | `10` | Game-years to play unless one nation captures 18 supply centers (SCs). |
| `--rounds N` | `3` | Negotiation rounds before each movement phase. `0` skips negotiation entirely. |
| `--power-model POWER=MODEL` *(repeatable)* | – | Give one power a different model than the default, so `--power-model TURKEY=claude-opus-4-7` means that Turkey's agent is Opus powered while all others use Sonnet. |
| `--memory N` | `3` | How many **movement turns** of memory each agent carries. Covers all three channels at once: the *"What happened in the last N turns"* narration recap, the agent's own strategy notes (2N of them, since each movement contributes initial + revised), and the dialogue history (older messages drop out of the prompt). `0` is a fully memoryless agent — only the current board, no recap. |
| `--power-memory POWER=N` *(repeatable)* | – | Override the memory depth for one power. E.g. `--power-memory TURKEY=5` lets Turkey remember 5 turns back while everyone else uses the default. |
| `--log-prompts` | off | Save every prompt each agent receives, paired with its response, to `prompts.jsonl` and `prompts.md`. |
| `--log-prompts-years N` | `1` | When `--log-prompts` is on, only log calls in the first N game-years. |
| `--with-commentary` | off | After the game finishes, also generate LLM strategic commentary and re-render so the slides include it. This is the "create the polished published dashboard" flag. |
| `--commentary-model MODEL` | same as `--model` | When `--with-commentary` is on, the model used for the commentary post-pass. |
| `--no-render` | off | Skip the dashboard render at end of game. Use this when you plan to run `render` separately, e.g. iterating on viewer code. |
| `--smoke` | off | Shortcut for cheap end-to-end verification: Haiku, 1 year, 1 round. |
| `--results-dir PATH` | `results` | Root directory for artifacts. |
| `--quiet` | off | Suppress the verbose phase-by-phase trace. |

### Options *not* in the CLI yet

- **Per-agent personality traits** (aggressive, untruthful, backstabbing, crazy)
  — currently every power shares the same persona prompt from
  [`personas/registry.py`](diplomacy_a2a/personas/registry.py). The programmatic
  `run_game(personas={"TURKEY": "<prompt>"})` already accepts per-power
  overrides; the CLI flag is **axis B** of the goal-3 experiments — design in
  [REFERENCE.md](REFERENCE.md).

## Code architecture

- **`diplomacy_a2a/llm/`** — All LLM calls go through one small interface
  called `LLMClient`, with `AnthropicClient` as its only implementation
  today. Adding another provider (OpenAI, Gemini, LiteLLM) means writing
  one new file against the same interface, not rewriting the rest of the
  project.
- **`diplomacy_a2a/personas/`** — default agent personas.
- **`diplomacy_a2a/game/`** — thin wrapper around
  [Meta's `diplomacy` library](https://github.com/diplomacy/diplomacy).
  No custom rules code.
- **Agent orchestration** — agents exchange private messages each turn,
  then commit orders, then Meta's `diplomacy` library adjudicates.
  See also **Negotiation protocol** below.
- **`results/`** — each game logs gameplay to
  `results/<run-id>/transcript.jsonl`, so `python -m diplomacy_a2a render
  results/<run-id>/ --with-commentary` then builds a dashboard for
  browsing the turn-by-turn movements, the agents' inter-turn
  negotiations, and the LLM-generated commentary on the play.

## What each agent knows

Diplomacy is a game of **open information**, and the simulation preserves that.
Each agent's per-turn view provides visibility across the **full board**
each turn:

- **Every power's unit positions** — not just its own; there is no fog of war.
- **Every supply center**, their owners, as well as the unowned neutral
  ones that are still grabbable.
- **Its own legal moves** for the upcoming phase.
- A plain-English **"what happened last turn"** recap (deterministic,
  generated from the orders + adjudication results, no LLM).

An agent does **not** see other powers' submitted orders, their legal-move lists,
or any private messages it wasn't party to — only its own correspondence.

Note that **agents do not have eyes**, and that the gameboard's geography
is not explicitly spelled out.
Agents' prompts do not include an adjacency table or any coordinate data.
Tactical correctness comes by prompting the agents with a list of legal-moves
(i.e. an illegal move simply isn't offered). That same list also implicitly
reveals adjacency: a province not in the list is not reachable in one turn
from the unit it would belong to, so strategic geographic reasoning beyond
that (e.g. "Galicia borders us both") relies on the model's built-in
knowledge of the standard Diplomacy map and the canonical province codes
(`GAL`, `BOH`, …). Negotiation messages from other powers can also leak
adjacency when a partner mentions a one-hop move (e.g. "I'll support A SIL
→ MUN" effectively asserts that SIL and MUN are adjacent). Positions are conveyed as **text** using those codes,
while the gameplay maps rendered by this project are for human viewers,
and not the agents.

## Negotiation protocol

Before each **movement** phase, agents negotiate over a configurable number of
rounds (set via `--rounds N`):

- **Within a round, messaging is simultaneous** — every power composes its
  outgoing messages from the same shared history, so a recipient doesn't see
  what you sent until the *next* round.
- **Negotiations across rounds is sequential** — round 2+ sees the prior
  rounds' incoming messages, so agents can react, counter, and confirm before
  committing.
- **Each agent chooses its own recipients** and **may stay silent** in any
  round.
- After the final round, each agent submits orders with the full dialogue in
  context, so deals and betrayals flow through to actual moves.

Agents are told this protocol explicitly: the round count, which round they're
in, the simultaneity, and that the final round is for closing. Which naturally
produces a deliberate *probe → negotiate → close* arc rather than repeated
openers.

## Agent strategy & memory

Beyond the dialogue history and the deterministic narration recap, each
agent also carries a self-authored **strategy log**, which is a private
record of what *it* thought it was doing each turn. On every movement phase each
agent writes a 1–2 sentence note, *twice*:

- **Before negotiation** — *initial strategy*: goals for the turn
  (e.g., *"I'll court Austria with vague promises while positioning to
  stab if opportunity arises"*), that are informed by the board and the
  agent's own strategy history from prior turns.
- **After the final round, before orders** — *revised strategy*: an
  updated stance reflecting what the negotiation actually produced.

Each agent is then given its strategy log history during subsequent
negotiations and moves, capped to the last `2 × --memory` entries, so
agents carry an explicit memory of their stated plans. Notes are
**private to each agent**, mirroring how Diplomacy works at a table, and
they are visible in the dashboard.

## Dashboard

By default, every run produces an HTML dashboard at
`results/<run-id>/dashboard/index.html`, navigable phase-by-phase (one
slide per phase). Each slide contains:

- **Orders and results maps**: what each unit was ordered to do that
  phase and the board after adjudication.
- **Plain-English narration** of what each power endeavored to do and
  how that turn was resolved.
- **LLM commentary**: an LLM-written strategic interpretation of the
  phase when `--with-commentary` is used.
- **Strategy notes**: each agent's initial and revised plans for the phase.
- **Negotiation transcripts**: a link to all agent-to-agent dialogue that
  preceded that phase's orders.
- **KPI charts**: each player's supply center (SC) counts as well as
  their Sum-of-Squares (SoS) score, where SoS = SC² / Σ(SC²).

## Summary of Main Findings *(placeholder)*

This section will summarize empirical results from the goal-3
controlled-variation experiments as they complete. Expected content:
per-axis takeaways (model capability, personality trait, memory depth,
pre-game collusion, information asymmetry), the success-vs-spend chart
described in goal 3, and any falsifiable claims that emerge about which
agent designs perform better in A2A competition.

Cost to execute the canonical game is about **$25 when using Sonnet**
(measured) with wall-time ≈2.6 hours. The canonical run processed about
**6.2M input tokens** (of which 2.1M were served from cache at 10% of
full price) and **360K output tokens**. Haiku and Opus runs at the same
configuration are extrapolated from per-token rate ratios: Haiku is
roughly 1/3 of Sonnet (≈$8), while Opus is roughly 5× Sonnet (≈$120).
Only Sonnet has been measured at the canonical configuration.


For additional project details see [**REFERENCE.md**](REFERENCE.md).

