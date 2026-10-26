#!/usr/bin/env bash
# W8 census (offline): stage 1 refit from observations only, then stage 2 scoring. No pixels, no MotionCorr.
# Usage: run_census.sh SRC_ARCHIVE_DIR H7A_RUNS_DIR
set -euo pipefail
SRC=$1; RUNS=$2
W=$(cd "$(dirname "$0")/.." && pwd)
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2
PY=(uv run --no-project --with numpy python -I)
"${PY[@]}" "$W/scripts/w8_admit.py" "$RUNS" "$W/results/admission.json"
"${PY[@]}" "$W/scripts/w8_refit.py" "$W/results/controls_v2.json" "$RUNS" "$W/results/refit.json"
"${PY[@]}" "$W/scripts/w8_score.py" "$SRC" "$RUNS" "$W/results/refit.json" "$W/results/score.json" "$W/results/census_tables.md"
