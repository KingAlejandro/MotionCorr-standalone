#!/bin/bash
# v5.1 Linux tests (fake child only, no MotionCorr child, j1, <=2 threads). Runs under lane.py: leases held, CPUs 32-47.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; R=$NS/receipts; PY=/home/ubuntu/.mc-venv/bin/python3
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
export V5_PIN_REPO_ROOT=$NS/source V5_PIN_PILOT_ROOT=$NS/pilot_v5_1 TMPDIR=$NS/v51_scratch
mkdir -p $TMPDIR
ulimit -v 4194304
echo "=== BEFORE $(date -u +%FT%TZ)"; uptime; free -m | head -2; df -h /tmp | tail -1; taskset -pc $$; ps -eo pid,psr,pcpu,user,args --sort=-pcpu | head -6 | cut -c1-140
cd $NS/pilot_v5_1/release_v5
/usr/bin/time -v -o $R/v51-linux-tests.time $PY -B tests/test_driver_v5_1.py $R/TEST_V51_linux_RESULT_$1.json > $R/test-v51-linux-$1.log 2>&1; echo "v51_linux_rc=$?" | tee $R/test-v51-linux-$1.rc
echo "=== AFTER $(date -u +%FT%TZ)"; uptime; du -sh $TMPDIR | cut -f1; ls $TMPDIR | wc -l
