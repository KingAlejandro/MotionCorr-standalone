#!/bin/bash
# IO-thread-cap probe wrapper: locks (GPU3 correctness + venue bench, flock -n, held to the end), pins, occupancy monitor, health before/after, then run_iothreads.py.
# usage: taskset -c 96-103 bash run_iothreads.sh
set -u
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-iot-20261026
SRC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src
BIN=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr
FIX=/mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01
T=$(cd "$(dirname "$0")" && pwd)
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f PYTHONDONTWRITEBYTECODE=1
source $T/c1_env.sh || exit 1
export OMP_NUM_THREADS=6 OPENBLAS_NUM_THREADS=1; unset OMP_PROC_BIND OMP_PLACES GLIBC_TUNABLES
L=$SC/logs; mkdir -p $L; cd $SC
[ "$(awk '/Cpus_allowed_list/{print $2}' /proc/self/status)" = 96-103 ] || { echo "not pinned" | tee $L/STOP; exit 1; }
exec 7>>/tmp/motioncorr-bench.lock; flock -n 7 || { echo "bench lock held: stop" | tee $L/STOP; exit 5; }
exec 6>>/tmp/motioncorr-gpu3-correctness.lock; flock -n 6 || { echo "GPU3 lock held: stop" | tee $L/STOP; exit 5; }
for f in /tmp/motioncorr-bench.lock /tmp/motioncorr-gpu3-correctness.lock; do echo "$f inode $(stat -c %i $f) acquired $(date -u +%FT%TZ)"; done | tee $L/locks.txt
echo "src HEAD $(git -C $SRC rev-parse HEAD) dirty-files $(git -C $SRC status --porcelain | wc -l)" | tee $L/pins.txt
sha256sum $BIN $FIX/movie.mrcs $FIX/RECEIPT.json $FIX/input.star $SRC/tools/profiling/lib/runner.py | tee -a $L/pins.txt
for h in 34e768128b83f7c94eb4a41ee6bb9a795c52c531a5d646ce4116df83d8d3535a 3b6126efcd601173df79ddc657f7c9f72ac257fddb256e9dc11d7953c6d25def 27d9a55b9318aaa3b89b200d7047670f766670babb0afb8b88956707f60608a6 ba3a39e59ca796b5dcaae0a41e0ded6f2c020e877d344a4aa182e4afebf8ac55 e77a51a220cb0d91f4ac3c7fac211876d0c6833f; do grep -q $h $L/pins.txt || { echo "pin mismatch $h" | tee $L/STOP; exit 4; }; done
( taskset -c 102,103 bash -c 'while :; do printf "%s\t%s\t%s\t%s\n" "$(date -u +%FT%T.%N)" "$(cut -d" " -f1 /proc/loadavg)" "$(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | tr "\n" ";")" "$(awk "/^cpu(9[6-9]|10[0-1]) /{b+=\$2+\$3+\$4+\$7+\$8+\$9} END{print b}" /proc/stat)"; sleep 1; done' > $L/monitor.tsv 2>&1 ) & MON=$!
trap 'kill $MON 2>/dev/null' EXIT
bash $T/c1_occ.sh iot-pre 3 || { echo "pre health failed" | tee $L/STOP; exit 3; }
date -u +%FT%TZ > $L/series.started
taskset -c 96-103 /home/alex/.mc-venv/bin/python3 $T/run_iothreads.py $SC/work > $L/series.log 2>&1; echo "series rc=$?" | tee $L/series.rc
date -u +%FT%TZ > $L/series.finished
bash $T/c1_occ.sh iot-post 3; echo "post health rc=$?" | tee -a $L/series.rc
