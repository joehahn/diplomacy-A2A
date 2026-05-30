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
players' orders. Every turn unfolds in parallel rather than in sequence:
all seven players negotiate simultaneously, write their orders in secret,
and the orders are then adjudicated as a single batch with no turn order.
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

## A visual dive into a representative game

**[Explore our canonical game](https://joehahn.github.io/diplomacy-A2A/results/20260529T225943Z/index.html)**,
which uses Sonnet to power seven AI agents across 5 game-years (10 movement
phases in total), with 3 rounds of inter-agent communication before each
movement. The dashboard shows the turn-by-turn movements of every army and
navy unit, full transcripts of the agent-to-agent (A2A) communications that
precede each turn, each agent's self-authored strategy notes, and an
LLM-generated summary of the gameplay describing which nations used A2A
negotiations to advance their goals, which agents fumbled, and who
backstabbed whom.

## Goals & deliverables

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
   transcript and the turn-by-turn slideshow are the deliverables that
   expose how effective those agents are at influencing each other, not
   whether any particular agent wins.

3. **Quantify what helps an AI agent succeed when it is competing against other agents in an A2A universe.** *(Under active development.)*
   Controlled A/B experiments where six agents are identical and one differs
   along a single axis: model capability (one Sonnet among Haikus, or one Opus
   among Sonnets), memory depth (one agent given more or less past-turn
   context), personality trait (one aggressive / untruthful / backstabbing
   agent at an otherwise neutral table), pre-game collusion (two agents
   share a private agreement injected into their dialogue history), or
   information asymmetry (one agent has parts of its prompt hidden, such as
   the current supply-center ownership tracker, forcing it to infer
   standings from unit positions and dialogue alone).

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
prices, traders never see opponents' positions. Axis E in Goal 3 above
is the experiment in this testbed that most directly probes that property.

The specific business analogy this project frames its findings against
will be selected in a future iteration.

## Status

Core game loop and CLI work end-to-end — see the committed canonical run
under `results/20260529T225943Z/` for representative output. The
controlled-variation experiments described in goal 3 are the current
in-progress work.

## Setup

Requires Python 3.10+ (developed on 3.12) and an Anthropic API key.

```bash
git clone <this repo>
cd diplomacy-A2A
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your key into .env
```

## Running

The CLI has three subcommands split along cost / LLM-use lines: **`run`**
executes a game (LLM, ≈$8-12), **`render`** rebuilds the dashboard from a
finished transcript (no LLM, sub-second), and **`commentary`** adds
LLM-written strategic commentary (≈$0.50). Invoking with no subcommand
defaults to `run`, so older one-line invocations keep working.

```bash
# default: one full Sonnet game, 5 years, 3 negotiation rounds, strategy log on
python -m diplomacy_a2a                      # equivalent to `... run`

# the canonical published demo: game + year-1 prompt dump + LLM commentary
python -m diplomacy_a2a --log-prompts --with-commentary

# cheap end-to-end verification (Haiku, 1 year, 1 round) — pennies
python -m diplomacy_a2a --smoke

# Opus showcase (more expensive, ≈$15+ at 5 years × 3 rounds × strategy on)
python -m diplomacy_a2a --model claude-opus-4-7

# per-power model override (axis-A experiment plumbing)
python -m diplomacy_a2a --power-model TURKEY=claude-opus-4-7

# per-power memory override
python -m diplomacy_a2a --power-memory TURKEY=10

# Re-render a finished run after tweaking viewer code (no LLM, free)
python -m diplomacy_a2a render results/20260529T225943Z/

# Add or refresh LLM commentary on a finished run, then re-render
python -m diplomacy_a2a render results/20260529T225943Z/ --with-commentary

# Generate commentary only (no render — useful in scripts)
python -m diplomacy_a2a commentary results/20260529T225943Z/

python -m diplomacy_a2a --help                # subcommand list
python -m diplomacy_a2a run --help            # game-execution options
python -m diplomacy_a2a render --help         # render + commentary options
```

Artifacts (transcript, maps, slideshow, report) land under `results/<run-id>/`.
The transcript is the canonical artifact; every renderer derives from it.

### Options

| Flag | Default | What it does |
|---|---|---|
| `--model MODEL` | `claude-sonnet-4-6` | Anthropic model id used as the default for every power. Sonnet is the workhorse — the canonical is Sonnet, and a 5-year game runs ≈$8. Use `claude-opus-4-7` for a stronger (≈$15+) showcase or `claude-haiku-4-5-20251001` for cheap experiments. |
| `--years N` | `5` | Game-years to play. Solo wins (18 SCs) end the game early regardless. |
| `--rounds N` | `3` | Negotiation rounds before each movement phase. `0` skips negotiation entirely. |
| `--power-model POWER=MODEL` *(repeatable)* | – | Give one power a different model than the default — weaker (Haiku) or stronger (Opus). E.g. `--power-model TURKEY=claude-opus-4-7` while everyone else stays on Sonnet. Costs are reported per-model. |
| `--memory N` | `3` | How many **movement turns** of memory each agent carries. Covers all three channels at once: the *"What happened in the last N turns"* narration recap, the agent's own strategy notes (2N of them, since each movement contributes initial + revised), and the dialogue history (older messages drop out of the prompt). `0` is a fully memoryless agent — only the current board, no recap. |
| `--power-memory POWER=N` *(repeatable)* | – | Override the memory depth for one power. E.g. `--power-memory TURKEY=10` lets Turkey remember 10 turns back while everyone else uses the default. |
| `--log-prompts` | off | Save every prompt each agent receives, paired with its response, to `prompts.jsonl` and `prompts.md`. See **Seeing the exact agent prompts and responses**. |
| `--log-prompts-years N` | `1` | When `--log-prompts` is on, only log calls in the first N game-years. |
| `--with-commentary` | off | After the game finishes, also generate LLM strategic commentary (`commentary.py`) and re-render so the slides include it. Adds ≈$0.50 of Sonnet calls. This is the "give me the polished published dashboard" flag. |
| `--commentary-model MODEL` | same as `--model` | When `--with-commentary` is on, the model used for the commentary post-pass. |
| `--no-render` | off | Skip the dashboard render at end of game (transcript still written). Use this when you plan to run `render` separately, e.g. iterating on viewer code. |
| `--smoke` | off | Shortcut for cheap end-to-end verification: Haiku, 1 year, 1 round. Pennies. |
| `--results-dir PATH` | `results` | Root directory for artifacts. |
| `--quiet` | off | Suppress the verbose phase-by-phase trace. |

**Strategy log is always on.** Each agent writes a 1–2 sentence strategy note
*before* negotiation and revises it *after*, and carries its own past notes
forward into every later call. This adds ≈25–35% to the per-game cost but
produces a much richer transcript. See **Agent strategy & memory** below.

### Options *not* in the CLI yet

- **Per-agent personality traits** (aggressive, untruthful, backstabbing, crazy)
  — currently every power shares the same persona prompt from
  [`personas/registry.py`](diplomacy_a2a/personas/registry.py). The programmatic
  `run_game(personas={"TURKEY": "<prompt>"})` already accepts per-power
  overrides; the CLI flag is **axis B** of the goal-3 experiments — design in
  [REFERENCE.md](REFERENCE.md).
- **Pre-game collusion** between two agents — **axis D** of the same.

### Cost / time per game

A `--smoke` run costs pennies. The canonical Sonnet run (5 years, 3 rounds,
strategy on, `--log-prompts` for year 1) is budgeted at ≈$8 and ≈80 min,
extrapolating from the older 2-year canonical (≈$3.20 / 28 min). Haiku is
≈⅓ the cost (prompt caching not yet firing on Haiku 4.5 — see
[REFERENCE.md](REFERENCE.md) known issues). A controlled-variation experiment
series (axis A–D) is budgeted under ≈$300 total. Per-model rates and full
per-run timing are in [REFERENCE.md](REFERENCE.md).

## Architecture

- **`diplomacy_a2a/llm/`** — `LLMClient` protocol (the seam) plus the single
  v1 `AnthropicClient` implementation. Designed so a second provider
  (OpenAI, LiteLLM, etc.) is a future ≈50-line addition, not a refactor.
- **`diplomacy_a2a/personas/`** — per-agent system prompts as markdown.
- **`diplomacy_a2a/game/`** — thin wrapper around
  [Meta's `diplomacy` library](https://github.com/diplomacy/diplomacy)
  (MIT, DATC-compliant). No custom rules code.
- **[`agent.py`](diplomacy_a2a/agent.py), [`negotiation.py`](diplomacy_a2a/negotiation.py),
  [`runner.py`](diplomacy_a2a/runner.py)** — the orchestration: agents exchange
  private messages each turn, then commit orders, then the library adjudicates.
  See **Negotiation protocol** below.
- **`results/`** — pre-rendered transcripts so visitors can see output
  without spending money. Each game renders a turn-by-turn HTML slideshow
  (maps, narration, agent strategies, dialogue) at
  `results/<run-id>/index.html`, hosted on GitHub Pages —
  [**view the canonical run**](https://joehahn.github.io/diplomacy-A2A/results/20260529T225943Z/index.html)
  (5 years, 3 rounds of negotiation per turn, strategy log + LLM commentary
  + year-1 prompt dump). The canonical configuration is
  `python -m diplomacy_a2a --log-prompts --with-commentary` — see
  [results/README.md](results/README.md).

## What each agent sees

Diplomacy is a game of **open information**, and the simulation preserves that.
Each agent's prompt is built by [`game/view.py`](diplomacy_a2a/game/view.py) and
contains the **full board** every turn:

- **Every power's unit positions** — not just its own; there is no fog of war.
- **Every supply center and who owns it**, with counts (so it knows the standings).
- **Its own legal moves** for the phase, computed by the library
  (`get_all_possible_orders`) and filtered to the units it controls — the
  authoritative list of what it may order.
- A plain-English **"what happened last turn"** recap (see Turn narration).

An agent does **not** see other powers' submitted orders, their legal-move lists,
or any private messages it wasn't party to — only its own correspondence.

**Geography is not spelled out.** There is deliberately no adjacency table or
coordinates in the prompt. Tactical correctness comes from the legal-moves list
(an illegal move simply isn't offered), and strategic geographic reasoning
("Galicia borders us both") relies on the model's built-in knowledge of the
standard Diplomacy map via the canonical province codes (`GAL`, `BOH`, …).
Positions are conveyed as **text**, using those codes — the rendered SVG maps
(with province labels) are for human readers, not the agents. If geography
hallucinations ever surface in transcripts, a compact adjacency table can be
added to the prompt as a cheap experiment.

## Negotiation protocol

Before each **movement** phase, agents negotiate over a configurable number of
rounds (`negotiation_rounds`, set when calling `run_game`):

- **Within a round, messaging is simultaneous** — every power composes its
  outgoing messages from the same shared history, so a recipient doesn't see
  what you sent until the *next* round.
- **Across rounds it is sequential** — round 2+ sees the prior rounds' incoming
  messages, so agents can react, counter, and confirm before committing.
- **Each agent chooses its own recipients** (any subset of the other powers)
  and **may stay silent** in any round.
- After the final round, each agent submits orders with the full dialogue in
  context, so deals (and betrayals) flow through to actual moves.

Agents are told this protocol explicitly — the round count, which round they're
in, the simultaneity, and that the final round is for closing — which produces a
deliberate *probe → negotiate → close* arc rather than repeated openers. The
mechanics live in [`agent.py`](diplomacy_a2a/agent.py) (`negotiate`, the system
prompt, dialogue formatting) and [`negotiation.py`](diplomacy_a2a/negotiation.py)
(`run_negotiation_round`); [`runner.py`](diplomacy_a2a/runner.py) drives the rounds.

## Agent strategy & memory

Beyond the dialogue history and the deterministic narration recap, each agent
also carries a self-authored **strategy log** — a private record of what
*it* thought it was doing each turn, generated by the runner without
any extra prompting from the user. (This was previously opt-in behind a
`--strategy` flag; it's now hardwired on because the artifacts the project
exists to produce are dramatically richer with it.)

On every movement phase the runner asks each power to write a 1–2 sentence
note twice:

- **Before negotiation** — *initial strategy*: goals for the turn (named powers,
  named provinces, intended deals), informed by the board and the agent's own
  strategy history from prior turns.
- **After the final round, before orders** — *revised strategy*: an updated
  stance reflecting what the negotiation actually produced (deals struck, refused,
  or broken).

Every subsequent call (later negotiation rounds, order submission, future turns)
is given **that agent's own strategy history** (capped to the last `2 × --memory`
entries — default 6, since `--memory` is 3 movement turns and each movement
contributes initial + revised), so agents carry an explicit, persistent memory
of their stated plans and how those plans evolved.

This makes the agents work smarter in three concrete ways:

1. **Planning-then-acting sharpens decisions.** Forcing the model to articulate
   a plan before it speaks or moves is a well-established way to make its
   reasoning more coherent — the strategy note functions as a brief planning
   step that constrains the negotiation messages and the orders that follow.
2. **Cross-turn memory of allies and rivals.** Without the log, an agent can
   forget a betrayal two turns ago. With it, the exact phrasing the agent itself
   wrote ("Russia stabbed me at Galicia in F1901M; treat as hostile.") is back
   in front of it next turn — far more reliable than re-inferring trust from
   positions and a long dialogue history.
3. **Observable intent.** Strategy notes are first-class artifacts: shown in the
   slideshow as a per-power collapsible block on each movement-phase slide, and
   captured in `prompts.md`. Detecting a betrayal becomes "stated goal X, did
   Y" — clean and unambiguous. This is also the per-persona behavioral
   fingerprint goal-3's personality experiment needs: aggressive, conservative,
   or backstabbing traits will produce visibly different strategy notes,
   complementing what dialogue alone shows.

Strategy notes are **private to each agent** (opponents see only the messages it
chooses to send, mirroring how Diplomacy works at a table). Cost: about
**+25–35% per game** — two extra short LLM calls per power per movement phase
plus a small token bump for carrying history. Always on; the previously-required
`--strategy` flag has been promoted to default behavior. Mechanics live in
[`agent.py`](diplomacy_a2a/agent.py) (`state_strategy` / `revise_strategy`) and
[`runner.py`](diplomacy_a2a/runner.py).

## Turn narration & observability

After each phase, a **deterministic plain-English narration** of what every
power did and how it resolved is generated straight from the orders + adjudication
results — e.g. *"AUSTRIA: A BUD → SER; F ALB supports A SER → GRE; ITALY: A VEN →
TRI (bounced)"*. No LLM, so it's faithful and reproducible
([`narration.py`](diplomacy_a2a/narration.py)). It serves two consumers:

- **Humans** — shown beside the maps on each slideshow/report phase, so the action
  reads at a glance instead of as raw order syntax.
- **Agents** — fed into each agent's view as a "what happened last turn" recap,
  so they reason about who supported or attacked whom from readable facts (and see
  *outcomes* like bounces/dislodgements that bare orders don't convey).

### Seeing the exact agent prompts and responses

For transparency/debugging, `--log-prompts` writes the exact **prompt** each
agent receives plus the **response** it produced to `results/<run-id>/prompts.jsonl`,
and renders a navigable, GitHub-friendly **`prompts.md`** alongside it
(collapsible per-call sections grouped by phase / round / power — skim the index,
click any prompt to expand). By default it only captures **the first game-year**,
which is where the opening negotiation/coordination is most legible and keeps the
artifact focused (`--log-prompts-years N` extends that).

The canonical run's dumps **are committed** so you can read precisely what
the agents said without spending anything:
[**`prompts.md`**](results/20260529T225943Z/prompts.md) (≈853 KB; GitHub
renders the collapsibles inline) or the raw
[`prompts.jsonl`](results/20260529T225943Z/prompts.jsonl) (≈778 KB). The
flag is off by default and otherwise gitignored, so a full experiment grid
isn't bloated with redundant dumps. To produce one yourself:

```bash
python -m diplomacy_a2a --log-prompts                       # game + dashboard
python -m diplomacy_a2a --log-prompts --with-commentary     # + LLM commentary
```

That's the bare canonical: 5-year, 3-round, Sonnet, strategy on, log year 1
(≈$8 / ≈80 min; `+$0.50` for the commentary post-pass with `--with-commentary`).
`--log-prompts` itself adds no API cost — it only saves prompts that are sent
anyway.

Separately, **optional LLM commentary** ([`commentary.py`](diplomacy_a2a/commentary.py))
can add a narrator's strategic read to each slide — who's threatening whom, who's
cooperating, who appears to have betrayed a promise — shown between the result map
and the negotiation. Unlike the deterministic narration, this is *interpretation*
(human-facing only, never fed to agents), so it's a separate opt-in pass over a
finished transcript (one LLM call per phase) rather than part of `run_game` — kept
out of the game loop so a full experiment grid stays cheap.

## Cost

A `--smoke` run costs pennies; the canonical (Sonnet, 5 years, 3 rounds,
strategy on, `--log-prompts` year 1, plus the LLM-commentary post-pass) came
in at **$11.98 + $0.50 = ≈$12.50** end-to-end and ≈77 min wall-time. A full
controlled-variation experiment series (axis A–D, see goal 3 and
[REFERENCE.md](REFERENCE.md)) is budgeted under **≈$300**.
Per-million-token rates, per-phase timing, and per-run cost history are
tracked in [REFERENCE.md](REFERENCE.md).

## Notes for re-running

LLM outputs are not byte-for-byte deterministic even at temperature 0,
so a rerun will produce *similar* dynamics, not identical transcripts.
Model IDs are pinned in `diplomacy_a2a/config.py` so reruns are
comparable across model releases.

For technical details (model pricing, per-phase timing observations,
quality notes, experiment results as they land, known issues): see
[**REFERENCE.md**](REFERENCE.md).

