#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# N3/N4 iteration 2 only (FROZEN-ITER2.md): five TEST-ONLY overlay builds, CPU and GPU1 runs, grade.
# No N1/N2 stages. Same lane, locks and stop-on-first-failure rules as ../tools/chain.sh.
# usage: G_SCR=<new scratch> G_SHA=<iteration-2 commit> chain_iter2.sh   (after ../tools/setup.sh)
set -u
D=$(cd "$(dirname "$0")/../tools" && pwd); I=$(cd "$(dirname "$0")" && pwd); source "$D/lane.sh" || exit 1
S=$G_SCR; PY=$G_PY; mkdir -p $S/logs
exec 7>"$G_CPU_LOCK"; flock -n 7 || { echo "CPU14-15 lease contended; stopping"; exit 5; }
flock -n /tmp/motioncorr-i61-cpu-14-15.lock true || { echo "i61 CPU14-15 lock held by another lane; stopping"; exit 5; }
echo "chain-iter2 $$ start $(date -u +%FT%TZ) sha=$G_SHA" >> $S/logs/CHAIN.txt
st() { "$D/stage.sh" "$@"; rc=$?; echo "$1 rc=$rc $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
       [ $rc -eq 0 ] || { echo "$1" > $S/logs/CHAIN.stopped_at; exit 1; }; }
st i2-health-start "$D/health.sh" i2-start
for arm in ov-base ov-cand ov-mut; do st i2-b-$arm-cpu env CFG=cpu "$D/build.sh" $S/src-$arm $S/build-$arm-cpu motioncorr; done
for arm in ov-base ov-cand; do st i2-b-$arm-cuda env CFG=cuda "$D/build.sh" $S/src-$arm $S/build-$arm-cuda motioncorr; done
st i2-n3-cpu $PY "$I/n3_iter2.py" run cpu
st i2-n3-gpu "$D/gpu_locked.sh" i2-n3-gpu $PY "$I/n3_iter2.py" run gpu
st i2-n3-grade $PY "$I/n3_iter2.py" grade
st i2-health-end "$D/health.sh" i2-end
echo "chain-iter2 $$ complete $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
