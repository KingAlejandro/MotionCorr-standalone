#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Frozen #264 native campaign (FROZEN.md). Sequential named stages; the first nonzero stage stops the chain.
# Holds the lane CPU lease for its lifetime. usage: G_SCR=... G_SHA=... chain.sh   (run detached; receipts in logs/)
set -u
D=$(cd "$(dirname "$0")" && pwd); source "$D/lane.sh" || exit 1
S=$G_SCR; PY=$G_PY; mkdir -p $S/logs
exec 7>"$G_CPU_LOCK"; flock -n 7 || { echo "CPU14-15 lease contended; stopping"; exit 5; }
flock -n /tmp/motioncorr-i61-cpu-14-15.lock true || { echo "i61 CPU14-15 lock held by another lane; stopping"; exit 5; }
echo "chain $$ start $(date -u +%FT%TZ) sha=$G_SHA" >> $S/logs/CHAIN.txt
st() { "$D/stage.sh" "$@"; rc=$?; echo "$1 rc=$rc $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
       [ $rc -eq 0 ] || { echo "$1" > $S/logs/CHAIN.stopped_at; exit 1; }; }
st health-start "$D/health.sh" start
# N1: candidate CPU, CUDA, CUDA+nvCOMP full build, collection and full CTest.
st b-cand-cpu env CFG=cpu "$D/build.sh" $S/src-cand $S/build-cand-cpu all
st ctest-cand-cpu "$D/ctest.sh" cpu
st b-cand-cuda env CFG=cuda "$D/build.sh" $S/src-cand $S/build-cand-cuda all
st ctest-cand-cuda "$D/ctest.sh" cuda
st b-cand-nvcomp env CFG=nvcomp "$D/build.sh" $S/src-cand $S/build-cand-nvcomp all
st ctest-cand-nvcomp "$D/ctest.sh" nvcomp
# N2: base vs candidate on the 24 tutorial movies, CPU then GPU1.
st b-base-cpu env CFG=cpu "$D/build.sh" $S/src-base $S/build-base-cpu motioncorr
st b-base-cuda env CFG=cuda "$D/build.sh" $S/src-base $S/build-base-cuda motioncorr
st n2-inputs $PY "$D/n2.py" inputs
st n2-base-cpu $PY "$D/n2.py" run base-cpu $S/build-base-cpu/motioncorr cpu
st n2-cand-cpu $PY "$D/n2.py" run cand-cpu $S/build-cand-cpu/motioncorr cpu
st n2-cmp-cpu $PY "$D/n2.py" compare base-cpu cand-cpu cpu
st n2-gpu "$D/gpu_locked.sh" n2-gpu bash -c "$PY $D/n2.py run base-gpu $S/build-base-cuda/motioncorr gpu && $PY $D/n2.py run cand-gpu $S/build-cand-cuda/motioncorr gpu"
st n2-cmp-gpu $PY "$D/n2.py" compare base-gpu cand-gpu gpu
# N3/N4: TEST-ONLY overlay builds through the real runner.
for arm in ov-base ov-cand ov-mut; do st b-$arm-cpu env CFG=cpu "$D/build.sh" $S/src-$arm $S/build-$arm-cpu motioncorr; done
for arm in ov-base ov-cand; do st b-$arm-cuda env CFG=cuda "$D/build.sh" $S/src-$arm $S/build-$arm-cuda motioncorr; done
st n3-cpu $PY "$D/n3.py" run cpu
st n3-gpu "$D/gpu_locked.sh" n3-gpu $PY "$D/n3.py" run gpu
st n3-grade $PY "$D/n3.py" grade
st health-end "$D/health.sh" end
echo "chain $$ complete $(date -u +%FT%TZ)" >> $S/logs/CHAIN.txt
