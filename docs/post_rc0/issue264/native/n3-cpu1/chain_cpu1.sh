#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# N3/N4 CPU subset (FROZEN-CPU1.md): no GPU query, CUDA configure, GPU lock or GPU run. Three CPU overlay builds,
# 24 CPU rows, original grade plus the CPU-subset verdict. First nonzero stage stops the chain; nothing retries.
# usage: G_SCR=<new scratch> G_SHA=<CPU-subset commit> taskset -c 14-15 chain_cpu1.sh   (after ../tools/setup.sh)
set -u
D=$(cd "$(dirname "$0")/../tools" && pwd); C=$(cd "$(dirname "$0")" && pwd); source "$D/lane.sh" || exit 1
S=$G_SCR; PY=$G_PY; mkdir -p $S/logs
exec 7>"$G_CPU_LOCK"; flock -n 7 || { echo "CPU14-15 lease contended; stopping"; exit 5; }
flock -n /tmp/motioncorr-i61-cpu-14-15.lock true || { echo "i61 CPU14-15 lock held by another lane; stopping"; exit 5; }
echo "chain-cpu1 $$ start $(date -u +%FT%TZ) sha=$G_SHA" >> $S/logs/CHAIN.txt
st() { "$D/stage.sh" "$@"; rc=$?; echo "$1 rc=$rc $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
       [ $rc -eq 0 ] || { echo "$1" > $S/logs/CHAIN.stopped_at; exit 1; }; }
st cpu1-occupancy-start "$C/occupancy_cpu.sh" cpu1-start
st cpu1-sources $PY "$C/check_sources.py"
for arm in ov-base ov-cand ov-mut; do st cpu1-b-$arm-cpu env CFG=cpu "$D/build.sh" $S/src-$arm $S/build-$arm-cpu motioncorr; done
st cpu1-receipts $PY "$C/n3_cpu1.py" receipts
st cpu1-n3-cpu $PY "$C/n3_cpu1.py" run cpu
st cpu1-grade $PY "$C/n3_cpu1.py" grade
st cpu1-occupancy-end "$C/occupancy_cpu.sh" cpu1-end
echo "chain-cpu1 $$ complete $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
