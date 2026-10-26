#!/bin/bash
# Native pilot r2 (continuation): under the pinned lane.py (all overlapping leases + bench lock held, taskset 32-47). Exactly the reviewed driver_v5_2 with --execute.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; O=$NS/native-run-r2; PY=/home/ubuntu/.mc-venv/bin/python3
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
{ echo "wrapper_pid=$$ ppid=$PPID start=$(date -u +%FT%TZ)"; taskset -pc $$; echo "held=$MOTIONCORR_HELD_LEASES"; uptime; free -m | sed -n 2p; df -h /tmp | tail -1; } > $O/wrapper.start 2>&1
cd $NS
$PY -B $NS/pilot_v5_2/release_v5_2/driver_v5_2.py --decision-dir $NS/decision-native-r2 --execute --receipt $O/RESULT.json > $O/driver.stdout 2> $O/driver.stderr
echo "driver_rc=$? end=$(date -u +%FT%TZ)" > $O/driver.rc
