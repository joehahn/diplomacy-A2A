# diplomacy-A2A

A Claude-powered, agent-to-agent simulation of the board game **Diplomacy**.
Persona-conditioned LLM agents negotiate, ally, and (often) betray each other
across multiple turns of full-press play. The artifact that matters is the
**negotiation transcript**, not whether any particular agent wins.

This is a portfolio demo for AI-consulting / forward-deployed-engineer work,
in the lineage of [CICERO](https://www.science.org/doi/10.1126/science.ade9097).

## Status

Under construction. Skeleton in place; game loop not yet wired up.

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

Entry points TBD. Once implemented:

```bash
python -m diplomacy_a2a smoke      # cheap end-to-end verification (~pennies)
python -m diplomacy_a2a run        # one full game
python -m diplomacy_a2a experiment # full persona × matchup × seed grid
```

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
  [**view the canonical run**](https://joehahn.github.io/diplomacy-A2A/results/20260524T034819Z/index.html)
  (with negotiation).

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

## Cost

TBD. A small-mode `smoke` run will cost pennies; a full grid will cost
~hundreds of dollars. Real numbers will land in this section once the
runner is wired up.

## Notes for re-running

LLM outputs are not byte-for-byte deterministic even at temperature 0,
so a rerun will produce *similar* dynamics, not identical transcripts.
Model IDs are pinned in `diplomacy_a2a/config.py` so reruns are
comparable across model releases.
