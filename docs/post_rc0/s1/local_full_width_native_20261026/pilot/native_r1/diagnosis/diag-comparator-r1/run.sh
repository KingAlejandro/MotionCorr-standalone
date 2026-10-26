#!/bin/bash
# Read-only diagnostic: the pinned comparator on SAVED trees only (baseline task copy / durable copy vs the produced OFF). Writes only to the new diag directory. Runs under lane.py.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; O=$NS/diag-comparator-r1; PY=/home/ubuntu/.mc-venv/bin/python3
CMP=$NS/source/docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py
OFF=$NS/evidence/noisy/OFF/output
TASK=/tmp/motioncorr-b2-factorial-20261026/evidence/runs/noisy/UP_only/output
DUR=/home/ubuntu/motioncorr-evidence/native-b2-upstream-factorial-20261026/task/evidence/runs/noisy/UP_only/output
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1
echo "comparator sha: $(sha256sum $CMP | cut -c1-64)"; uptime; taskset -pc $$
echo "== A) gate-style invocation (root A = durable copy), reproduces the retained STOP"; $PY -B $CMP $DUR $OFF $O/compare_durable_root.json; echo "rc=$?"
echo "== B) root A = the baseline copy at the ORIGINAL scratch root"; $PY -B $CMP $TASK $OFF $O/compare_original_root.json; echo "rc=$?"
echo "== before/after hashes of the saved trees"; (cd $OFF && find . -type f | sort | xargs sha256sum | sha256sum); (cd $TASK && find . -type f | sort | xargs sha256sum | sha256sum)
