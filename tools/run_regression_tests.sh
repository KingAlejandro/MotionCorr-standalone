#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MC_BIN="${1:-${REPO_ROOT}/build/motioncorr}"

if [[ ! -x "${MC_BIN}" ]]; then
    echo "ERROR: Executable not found at ${MC_BIN}"
    echo "Please build motioncorr first: cmake -S . -B build && cmake --build build"
    exit 1
fi

TMP_RUN_DIR="$(mktemp -d -t mc_test_XXXXXX)"
trap 'rm -rf "${TMP_RUN_DIR}"' EXIT

echo "=== Running MotionCorr Synthetic Fixture Parity Test ==="
echo "Binary: ${MC_BIN}"
echo "Run directory: ${TMP_RUN_DIR}"

(
  cd "${REPO_ROOT}/test-data/fixtures"
  "${MC_BIN}" \
    --i synthetic_128x128_8frames.star \
    --o "${TMP_RUN_DIR}" \
    --use_own --j 1 > /dev/null 2>&1
)

python3 "${REPO_ROOT}/tools/compare_motioncorr.py" \
  --ref "${REPO_ROOT}/test-data/fixtures/reference_output" \
  --test "${TMP_RUN_DIR}" \
  --ground-truth "${REPO_ROOT}/test-data/fixtures/synthetic_128x128_8frames_ground_truth.json" \
  --gate exact

echo "=== Regression Test Passed Successfully! ==="
