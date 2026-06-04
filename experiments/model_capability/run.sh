#!/usr/bin/env bash
#
# Axis A (model capability) driver: 7 games, each with one Opus "champion"
# seat and one Haiku "underdog" seat placed on opposite corners of the board,
# the other five seats on the Sonnet field default. Across the 7 games every
# power plays Opus exactly once and Haiku exactly once, so the headline metric
# is a within-power paired delta (see REFERENCE.md, Axis A).
#
# Reproducibility note: LLM play is not seeded, so this replays the identical
# *configuration* (models, rotation, years, rounds), not the identical
# transcript. The committed transcripts stay the canonical record; a rerun is
# a fresh, comparably-configured game.
#
# Usage:
#   source .venv/bin/activate   # needs an Anthropic key in .env
#   experiments/model_capability/run.sh
#
# Override models without editing the file:
#   OPUS_MODEL=claude-opus-4-7 experiments/model_capability/run.sh
#
set -euo pipefail

OPUS_MODEL="${OPUS_MODEL:-claude-opus-4-8}"
HAIKU_MODEL="${HAIKU_MODEL:-claude-haiku-4-5-20251001}"
CATEGORY="${CATEGORY:-model-capability}"

# Run from the repo root so `python -m diplomacy_a2a` finds the package.
cd "$(dirname "$0")/../.."

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Rotation: "OPUS_CHAMPION HAIKU_UNDERDOG", one entry per game. A single
# 5-cycle (England, Austria, France, Russia, Italy, back to England) plus a
# Germany/Turkey swap; every pair is an opposite-corner matchup.
ROTATION=(
  "ENGLAND AUSTRIA"
  "AUSTRIA FRANCE"
  "FRANCE RUSSIA"
  "RUSSIA ITALY"
  "ITALY ENGLAND"
  "GERMANY TURKEY"
  "TURKEY GERMANY"
)

echo "Axis A model-capability run: ${#ROTATION[@]} games"
echo "  Opus  = ${OPUS_MODEL}"
echo "  Haiku = ${HAIKU_MODEL}"
echo "  field = Sonnet (CLI default), output under results/${CATEGORY}/"
echo

game=0
for pair in "${ROTATION[@]}"; do
  game=$((game + 1))
  read -r opus haiku <<< "$pair"
  echo "=== Game ${game}/${#ROTATION[@]}: ${opus}=Opus vs ${haiku}=Haiku ==="
  # --no-render skips the per-game dashboard; render the 2-3 showcase games
  # afterward with `python -m diplomacy_a2a render <run-dir> --with-commentary`.
  python -m diplomacy_a2a run \
    --power-model "${opus}=${OPUS_MODEL}" \
    --power-model "${haiku}=${HAIKU_MODEL}" \
    --category "${CATEGORY}" \
    --no-render
  echo
done

echo "All ${#ROTATION[@]} games complete. Transcripts under results/${CATEGORY}/"
echo "Each run is self-describing: its run_started record stores power_models,"
echo "so analysis recovers the Opus/Haiku assignment from the transcript."
