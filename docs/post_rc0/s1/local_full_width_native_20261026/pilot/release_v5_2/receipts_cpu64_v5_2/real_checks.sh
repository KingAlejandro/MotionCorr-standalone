#!/bin/bash
# Real-path checks for v5.2 on cpu64, NO producer: (a) driver_v5_2 dry run (all 152 baseline bytes + root audit of 8 baselines + the frozen first OFF inventory + guard), (b) the unchanged comparator through pre_ON_gate on the saved noisy OFF in a scratch decision dir (positive control). Under lane.py.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; O=$NS/diag-continuation-r2; PY=/home/ubuntu/.mc-venv/bin/python3; R=$NS/pilot_v5_2/release_v5_2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
echo "start $(date -u +%FT%TZ)"; uptime; taskset -pc $$; echo "held=$MOTIONCORR_HELD_LEASES"
echo "== (a) dry run"; $PY -B $R/driver_v5_2.py --decision-dir $NS/decision-dryrun-r2 --receipt $O/dryrun_continuation.json > $O/dryrun_continuation.stdout 2> $O/dryrun_continuation.stderr; echo "dryrun_rc=$?"
echo "== (b) proof"; $PY -B - <<PY2 > $O/proof_pre_on.json 2> $O/proof_pre_on.stderr; echo "proof_rc=$?"
import sys, json
sys.path.insert(0, '$R')
import pair_decision_v5_2 as P
rec = P.pre_ON_gate('noisy', decision_dir='$NS/diag-proof-r2')
print(json.dumps({'status': rec['status'], 'binding_sha256': rec['binding_sha256'], 'comparator': rec['bound']['comparator'], 'binary_sha256': rec['bound']['binary_sha256']}, indent=1))
PY2
echo "== state"; ls $NS/evidence $NS/decision-dryrun-r2 2>&1 | head -4; ls $NS/diag-proof-r2 $NS/diag-proof-r2/pre_on/noisy 2>&1 | head; echo "end $(date -u +%FT%TZ)"
