#!/bin/bash
# Dry-run validation of the real pins (no producer, no movie). Runs under lane.py: leases held, CPUs 32-47.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; R=$NS/receipts; PY=/home/ubuntu/.mc-venv/bin/python3
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
echo "=== BEFORE $(date -u +%FT%TZ)"; uptime; free -m | head -2; df -h /tmp | tail -1; taskset -pc $$; echo "held=$MOTIONCORR_HELD_LEASES"
$PY -B $NS/pilot/release_v5/driver_v5.py --decision-dir $NS/decision-dryrun-1 --receipt $R/dryrun-1.json > $R/dryrun-1.stdout 2> $R/dryrun-1.stderr; echo "dryrun_rc=$?" | tee $R/dryrun-1.rc
echo "=== AFTER $(date -u +%FT%TZ)"; uptime; ls $NS | head -20; ls $NS/evidence 2>&1 | head -2
