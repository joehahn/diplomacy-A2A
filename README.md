# diplomacy-A2A

![Players at a Diplomacy board mid-negotiation](assets/diplomacy-board.jpg)

<sub>*Players hunched over a Diplomacy board at the Deskohraní 2008 board-game
festival. Photo by Matěj Baťha,
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), via
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Deskohran%C3%AD_2008_269.jpg).
This project does the same thing — six players plotting, allying, and betraying
each other across a Europe map — with LLM agents instead of humans.*</sub>

A Claude-powered, agent-to-agent simulation of the board game **Diplomacy**.
Persona-conditioned LLM agents negotiate, ally, and (often) betray each other
across multiple turns of full-press play. The artifact that matters is the
**negotiation transcript**, not whether any particular agent wins.

This is a portfolio demo for AI-consulting / forward-deployed-engineer work,
in the lineage of [CICERO](https://www.science.org/doi/10.1126/science.ade9097).

## Goals & deliverables

1. **Built with Claude Code, but reproducible with just an Anthropic key.**
   The project is *developed* using Claude Code, yet it *runs* on nothing more
   than the [Anthropic SDK](https://docs.anthropic.com/en/api/client-sdks)
   (`anthropic`) and an API key — Claude Code is the development harness, not a
   runtime dependency. Anyone can clone this, drop in their key, and rebuild or
   re-run the simulation. The provider boundary is a single seam
   ([`llm/client.py`](diplomacy_a2a/llm/client.py)).

2. **Highlight agent-to-agent interactions that move each other.** The point is
   not just that agents *send* messages, but that they *influence* one another —
   proposing, reacting across rounds, honoring or betraying deals — and that
   those interactions visibly drive how the game evolves. The negotiation
   transcript and the turn-by-turn slideshow are the deliverable (see
   **Negotiation protocol**), not whether any particular agent wins.

3. **Personality → success (the ultimate aim).** Condition each agent with a
   character trait — aggressive, conservative, backstabbing, untruthful,
   cooperative, … — and run enough games to ask: *which personality most
   reliably achieves success?* The [persona system](diplomacy_a2a/personas/)
   is the lever; the transcripts (the "why") plus game outcomes (the "what")
   are the data.

## Roadmap

Building toward goal 3:

- **Controlled-variation persona experiments** — instead of a full N-persona grid,
  hold 6 agents identical and vary *one* thing to get a clean A/B causal signal.
  Four planned axes:
  *(A)* model capability — one Sonnet among Haikus;
  *(B)* personality trait — one aggressive / untruthful / backstabbing / crazy
  agent in an otherwise neutral table;
  *(C)* memory depth — one agent given more or less past-turn context than the rest;
  *(D)* two-agent collusion — a pre-game shared agreement injected only into two
  agents' dialogue history.
  Sharper questions per dollar than a full grid (~$300 for v1 vs ~$600);
  produces falsifiable, comparable claims like *"a single Sonnet among six Haikus
  gains X more SCs on average"* and *"two colluding agents jointly out-perform
  the table by Y."*
- **Outcome scoring + analysis** — per-game scorer (`score.py`) emitting solo
  rate, survival rate, average SC, **Sum-of-Squares share**, peak SC, year-to-N,
  plus behavioral metrics (promise→action fidelity, alliance duration) — so the
  controlled experiments above resolve to data, not anecdote.
- **Player-KPI timeseries on the canonical-game dashboard** — phase-by-phase line
  plots of each power's **SC count** and **SoS share** over the course of a single
  game, embedded on the slideshow's index (or as a dedicated `dashboard.html`).
  Makes trajectory legible at a glance — *"Russia peaked at 7 in F1903M then
  collapsed"* — and complements the per-phase commentary.
- **Cheap "smoke" mode** — a one-game Haiku entry point so anyone can verify the
  whole pipeline end-to-end for pennies before committing to a full run. *(Done:
  `python -m diplomacy_a2a --smoke`.)*
- **Full order visibility (tabletop-faithful)** *(nice-to-have, not core)* —
  after each turn, show agents the complete set of submitted orders and how they
  resolved, the way players around a table see every order at the reveal. Today
  agents see only the resulting board, and illegal orders are dropped before
  anyone sees them. Surfacing orders would also let agents *deliberately* submit
  unusual or illegal orders as bluffs/signals — an order-level deception channel
  to complement the message-level lying that personalities will already do.

## Status

Under construction. Core game loop works end-to-end via `run_game`
([`runner.py`](diplomacy_a2a/runner.py)) — see committed runs under `results/`.
The documented CLI subcommands are still aspirational (not yet wired up).

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

```bash
# default: one full Opus game, 2 years, 3 negotiation rounds
python -m diplomacy_a2a

# cheap end-to-end verification (Haiku, 1 year, 1 round) — pennies
python -m diplomacy_a2a --smoke

# Sonnet, also save every agent prompt + response (first year, see below)
python -m diplomacy_a2a --model claude-sonnet-4-6 --log-prompts

python -m diplomacy_a2a --help     # full option list
```

Artifacts (transcript, maps, slideshow, report) land under `results/<run-id>/`.
A `--smoke` run costs pennies; a full Sonnet game runs ~$2; a full grid of
persona × matchup × seed experiments will run ~hundreds of dollars (see **Cost**).

## Architecture

- **`diplomacy_a2a/llm/`** — `LLMClient` protocol (the seam) plus the single
  v1 `AnthropicClient` implementation. Designed so a second provider
  (OpenAI, LiteLLM, etc.) is a future ~50-line addition, not a refactor.
- **`diplomacy_a2a/personas/`** — per-agent system prompts as markdown.
- **`diplomacy_a2a/game/`** — thin wrapper around
  [Meta's `diplomacy` library](https://github.com/diplomacy/diplomacy)
  (MIT, DATC-compliant). No custom rules code.
- **[`agent.py`](diplomacy_a2a/agent.py), [`negotiation.py`](diplomacy_a2a/negotiation.py),
  [`runner.py`](diplomacy_a2a/runner.py)** — the orchestration: agents exchange
  private messages each turn, then commit orders, then the library adjudicates.
  See **Negotiation protocol** below.
- **`results/`** — pre-rendered transcripts so visitors can see output
  without spending money. Flip through a game phase by phase in the
  turn-by-turn viewer (hosted on GitHub Pages):
  [**view the canonical run**](https://joehahn.github.io/diplomacy-A2A/results/20260528T214253Z/index.html)
  (3 rounds of negotiation per turn, turn-by-turn narration, and the new
  `--strategy` log per agent).

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

## Agent strategy & memory (`--strategy`)

By default an agent's only "memory" across turns is the dialogue history and the
deterministic narration recap — it can *infer* allies and enemies from positions
and conversations, but it has no explicit recollection of "Russia stabbed me last
fall" beyond what's parseable from the board.

`--strategy` adds a self-authored **strategy log** per agent. On every movement
phase the runner asks each power to write a 1–2 sentence note twice:

- **Before negotiation** — *initial strategy*: goals for the turn (named powers,
  named provinces, intended deals), informed by the board and the agent's own
  strategy history from prior turns.
- **After the final round, before orders** — *revised strategy*: an updated
  stance reflecting what the negotiation actually produced (deals struck, refused,
  or broken).

Every subsequent call (later negotiation rounds, order submission, future turns)
is given **that agent's own strategy history** (capped to the last 6 entries),
so agents carry an explicit, persistent memory of their stated plans and how
those plans evolved.

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
plus a small token bump for carrying history. Opt in with `--strategy`; off by
default. Mechanics live in
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
[**`prompts.md`**](results/20260528T214253Z/prompts.md) (≈ 836 KB; GitHub
renders the collapsibles inline) or the raw
[`prompts.jsonl`](results/20260528T214253Z/prompts.jsonl).

The flag is off by default and otherwise gitignored, so a full experiment grid
isn't bloated with redundant dumps. To produce one yourself:

```bash
python -m diplomacy_a2a --model claude-sonnet-4-6 --log-prompts
```

That's a full 2-year, 3-round game (~$2–2.5 on Sonnet); `--log-prompts` itself
adds no API cost — it only saves prompts that are sent anyway.

Separately, **optional LLM commentary** ([`commentary.py`](diplomacy_a2a/commentary.py))
can add a narrator's strategic read to each slide — who's threatening whom, who's
cooperating, who appears to have betrayed a promise — shown between the result map
and the negotiation. Unlike the deterministic narration, this is *interpretation*
(human-facing only, never fed to agents), so it's a separate opt-in pass over a
finished transcript (one LLM call per phase) rather than part of `run_game` — kept
out of the game loop so a full experiment grid stays cheap.

## Cost

TBD. A small-mode `smoke` run will cost pennies; a full grid will cost
~hundreds of dollars. Real numbers will land in this section once the
runner is wired up.

## Notes for re-running

LLM outputs are not byte-for-byte deterministic even at temperature 0,
so a rerun will produce *similar* dynamics, not identical transcripts.
Model IDs are pinned in `diplomacy_a2a/config.py` so reruns are
comparable across model releases.
