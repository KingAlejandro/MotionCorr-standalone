#!/bin/bash
# usage: run_noisy_diag.sh   (on cpu64) The one discriminating run of noisy_diagnosis/PREDICTION.md: noisy only, DCg + H2 global,
# --max_iter 5 --experimental_align_tolerance 1e-9 (global alignment forced to 5 iterations; patch alignment as in the production stop).
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
V=$DS_SC/v2; R=$V/receipts-h4; BIN=$DS_SC/build-h4on/motioncorr
DS_ONLY_CASES=noisy lane env DS_ONLY_CASES=noisy MC_EXPERIMENT_CCF_DC_ARM=global $DS_PY -I $D/ds_run_v2_cases.py $V diag-dcgh2g-g5 cpu $BIN cap $DS_CPUS "--experimental_coupled_peak global --max_iter 5 --experimental_align_tolerance 1e-9" > $R/diag-dcgh2g-g5.driver.out 2>&1
echo "diag run exit $?"
