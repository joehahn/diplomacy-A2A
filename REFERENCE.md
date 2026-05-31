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
| 20260529T225943Z *(previous canonical, 5-yr)* | Sonnet | 3 rounds, 5 yr, strategy on, `--log-prompts`, per-power placeholder personas | 18 | 4479s | **≈249** | **$11.98** + $0.50 commentary |
| 20260531T202425Z **(canonical, 10-yr)** | Sonnet | 3 rounds, 10 yr, strategy on, `--log-prompts`, uniform baseline persona, post-SC-importance rules | 36 | 9434s | **≈262** | **$24.69** + commentary |

**Headline:** Haiku is ≈3–4× faster than Sonnet *per phase on simple workloads*
(1 round, no strategy log). On the current canonical workload (3 rounds × strategy
log, the default) the per-phase advantage **collapses to roughly parity** because
per-phase call count dominates — Haiku doesn't make fewer calls than Sonnet, and
the strategy + 3-round combo is call-heavy. Cost is still ≈1/3 across the board.

---

## Quality observations

### Sonnet (canonical model)

Produces tight 1–2-sentence strategy notes, clearly probes in early
negotiation rounds, closes deals in round 3, and lets dialogue visibly
steer orders. The current canonical (`20260531T202425Z`,
`python -m diplomacy_a2a run --log-prompts --with-commentary`) played 10
game-years to F1910M and ended with two leaders tied at 8 SCs (England,
France), two near-eliminated (Germany at 2, Austria at 1), and three in
the middle (Italy, Russia, Turkey each at 5). The LLM commentary flagged
several agents publicly debunking each other's strength claims using
geography reasoning, e.g., *"Austria correctly identified that Turkey's
'strength 4' attack on BUD was mathematically impossible (CON, ANK, SMY
can't reach BUD in one move; F BLA can't support a land attack)"* — the
adjacency-inference behavior the rules.md Geography & adjacency section
was designed to enable. The previous 5-year Sonnet canonical
(`20260529T225943Z`, kept for behavioral comparison) is described in
"Old vs new canonical: behavioral comparison at year 5" above.

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

### Old vs new canonical: behavioral comparison at year 5

Compares the first 5 years of:

- **Old** (`20260529T225943Z`): 5 years, per-power placeholder personas
  (France conservative, Germany opportunist, Austria defensive, etc.),
  pre-SC-importance rules.md.
- **New** (`20260531T202425Z`): 10 years, uniform `BASELINE_PERSONA`
  across all 7 powers, rules.md with the added SC-importance paragraph
  and Geography & adjacency section.

Three variables changed at once (persona, prompt content, length), so
this is not a controlled axis-A test; it answers "do these three
changes together produce different play?" not "which change caused
what?". Goal-3's axis A and axis B will isolate the variables.

**Quantitative differences at end of F1905M:**

| Metric | OLD | NEW |
|---|---:|---:|
| Phases played to Y5 | 18 | 14 |
| Aggressive % (move + support-move / all movement orders) | 34.5% | 41.9% |
| Bounced units | 40 | 49 |
| Dislodged units | 7 | 4 |
| Std dev of SC counts at F1905M | 1.07 | 0.90 |
| Powers ≤ 2 SCs (near elimination) | 0 | 0 |
| Powers ≥ 7 SCs (dominant) | 0 | 0 |

**Per-power aggressiveness shift:**

| Power | OLD | NEW | Δ |
|---|---:|---:|---:|
| Austria | 26.7% | 52.3% | **+25.6 pp** |
| Italy | 41.0% | 55.3% | +14.2 pp |
| Russia | 28.6% | 39.1% | +10.6 pp |
| France | 40.0% | 47.5% | +7.5 pp |
| Germany | 29.8% | 31.0% | +1.2 pp |
| England | 34.2% | 31.8% | -2.4 pp |
| Turkey | 47.1% | 37.1% | -9.9 pp |

The biggest mover is Austria: under the old "defensive and central; hold
the position, broker peace" placeholder persona, Austria played 26.7%
active moves; under the uniform baseline, Austria becomes the *most*
aggressive of all 7 powers at 52.3%. Italy and Russia shift toward
attack-heavy play as well. Turkey moves the other way (from the old
"patient and long-game" placeholder to slightly less aggressive baseline
play).

**Tactical sophistication signal:** Bounces increase but dislodgements
decrease. More attacks meet equal-strength supports rather than
dislodging undefended units. Consistent with agents coordinating
defensive support orders better, or with offensive attacks being more
predictable to defenders.

**Opening strategy notes are remarkably similar across both runs.**
S1901M strategy notes hit the canonical Diplomacy openings in both
games (Austria → Balkans, England → Norway + North Sea, Germany →
Holland + Denmark, etc.). The per-power placeholder personas in OLD
didn't drive much opening differentiation; the uniform baseline doesn't
lose any opening quality.

**Y5 doesn't yet show divergence; Y10 does.** OLD's final F1905M
standings: GER 6 / RUS 6 / AUS 5 / FRA 5 / ITA 5 / ENG 4 / TUR 3 (no
eliminations, no dominant power). NEW's F1905M standings are similarly
balanced: ENG 6 / FRA 6 / AUS 5 / GER 5 / RUS 4 / ITA 4 / TUR 4. But
by F1910M (the new run's full length), NEW shows ENG 8 / FRA 8 / ITA 5
/ RUS 5 / TUR 5 / GER 2 / AUS 1 — two leaders tied at 8 SCs, Austria
effectively eliminated. **A 5-year window misses the asymmetry the
new prompt produces; 10 years reveals it.**

**LLM commentary highlights from the new run** (the commentary captures
agents using geography reasoning to debunk each other's claims, which
the new rules.md Geography & adjacency section was designed to enable):

- F1907M: *"Austria successfully called Russia's bluff: Moscow claimed
  'strength 2' on RUM but A MOS cannot reach RUM in one move..."*
- F1909M: *"Austria correctly identified that Turkey's 'strength 4'
  attack on BUD was mathematically impossible (CON, ANK, SMY can't
  reach BUD in one move; F BLA can't support a land attack)..."*
- F1910M: *"Russia successfully took RUM by coordinating A SEV→RUM with
  A GAL support at strength 2, finally breaking Austria's long-held
  defense — but only after Turkey's late pivot away from RUM
  (redirecting to BUL instead) cleared the path; Turkey's 'generous'
  concession of RUM was driven by Italy's pressure to vacate BUD, not
  altruism."*

These dialogue patterns are more analytically sophisticated than the
old canonical's typical phase commentary, which tended to describe
orders rather than analyze inter-power claims.

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

## Controlled-variation experiments

Goal 3 in the README is N-1-identical / 1-varied A/B comparisons across four
axes, replacing the original full persona grid. Each axis lands here as it
runs, with method + per-power results table + verdict.

### Axis A — model capability (one stronger model in a homogeneous table)

**Method:** 6 Sonnets + 1 Opus (rotating which power is the upgraded one,
across seeds), paired with an all-Sonnet baseline at identical settings.
3 rounds of negotiation per movement phase, strategy log on (hardwired in
the current default), 10 game-years each — same shape as the canonical
configuration so the only thing varying is the upgraded power.

Invocation:
```bash
python -m diplomacy_a2a run --power-model TURKEY=claude-opus-4-7 --log-prompts
```

**Status:** *Plumbing landed in commit `7358cdd` (run_game `power_clients`
+ `--power-model POWER=MODEL` CLI flag + model-aware cost estimator). First
runs pending.*

Results will land here when complete.

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
per phase of Sonnet calls (e.g. ≈$1 for a 36-phase game, ≈$0.50 for an
18-phase game); `--with-commentary` rolls game + commentary + re-render
into one command. A `--smoke` run (Haiku, 1 year, 1 round) costs pennies.

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

### Adjacency table fallback

Agents currently rely on the model's training-data knowledge of the
standard Diplomacy map plus the canonical province codes (`GAL`, `BOH`,
…) for spatial reasoning. If geography hallucinations ever surface in
transcripts, a compact adjacency table can be added to the prompt as a
cheap experiment.
