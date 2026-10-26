#!/bin/bash
# i8 multi-device window: all four canonical GPU locks taken nonblocking (contention = stop, no retry), bench lock only probed and recorded (never taken),
# no compute process on any GPU, health of all four GPUs before and after (post failure -> exit 37), the driver runs pinned to the granted CPUs 96-103.
# usage: c1_mg.sh LABEL cmd...   (run through c1_stage.sh)
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
label=$1; shift
export QF_W=$C1_SCR QF_MG_W1_GPU=3 QF_MG_CPU_ALL=$C1_CPUS; cd $C1_SCR
exec 9>/tmp/motioncorr-gpu0-correctness.lock; flock -n 9 || { echo "gpu0 lease contended; stopping"; exit 5; }
exec 8>/tmp/motioncorr-gpu1-correctness.lock; flock -n 8 || { echo "gpu1 lease contended; stopping"; exit 5; }
exec 7>/tmp/motioncorr-gpu2-correctness.lock; flock -n 7 || { echo "gpu2 lease contended; stopping"; exit 5; }
exec 6>/tmp/motioncorr-gpu3-correctness.lock; flock -n 6 || { echo "gpu3 lease contended; stopping"; exit 5; }
( exec 5>$C1_BENCH_LOCK; if flock -n 5; then echo "bench lock probe: free"; else echo "bench lock probe: HELD (not waited on, not touched)"; fi ) | tee $C1_SCR/logs/$label.bench-probe
echo "locks held $(date -u +%FT%TZ)"
"$D/c1_occ.sh" $label-pre 0,1,2,3; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
export PATH=/home/alex/.mc-venv/bin:$PATH
taskset -c $C1_CPUS "$@"; rc=$?
"$D/c1_occ.sh" $label-post 0,1,2,3; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
echo "driver rc=$rc locks released $(date -u +%FT%TZ)"
exit $rc
