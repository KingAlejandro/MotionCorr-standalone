#!/bin/bash
set -eu
ROOT=/mnt/clathrin/mc-d3-classifier-20261022
cd "$ROOT"
export PATH=/usr/local/cuda-12.8/bin:/home/alex/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
export MC_D3_SAMPLE_GUARD="$ROOT/src/docs/rc0/issue226/d3/classifier_cleanup_20261022/sample_guard.py"
export MC_D3_HEALTH_BASELINE="$ROOT/health-baseline.json"
mode=$1
trap 'code=$?; date -u; echo "$code" > "driver-$mode.exit"; exit "$code"' EXIT
printf '%s\n' "$$" > "driver-$mode.pid"
date -u
hostname
taskset -pc $$
case "$mode" in
build-before|build-before-clean|build-after|build-final)
    exec 8>/tmp/motioncorr-build.lock
    flock -n 8
    cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DUSE_NVCOMP=OFF \
        -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
    cmake --build build --parallel 2 --target motioncorr_streaming_plan_fault motioncorr_faultinject
    sha256sum build/motioncorr_streaming_plan_fault build/motioncorr_faultinject
    ;;
before|after|final)
    exec 9>/tmp/motioncorr-gpu3-correctness.lock
    flock -n 9
    "$MC_D3_SAMPLE_GUARD" pre "$ROOT/$mode-initial"
    if [ "$mode" = before ]; then
        /home/alex/.mc-venv/bin/python3 src/tests/run_streaming_plan_classification_cleanup.py \
            --binary build/motioncorr_streaming_plan_fault --root "$ROOT/before" \
            --cases make-fatal-cleanup-success make-fatal-cleanup-alloc
    elif [ "$mode" = final ]; then
        /home/alex/.mc-venv/bin/python3 src/tests/run_streaming_plan_classification_cleanup.py \
            --binary build/motioncorr_streaming_plan_fault --root "$ROOT/final" \
            --cases create-fatal cleanup-fatal make-fatal-cleanup-success \
                make-fatal-cleanup-alloc auto-fatal-cleanup-alloc make-alloc-cleanup-fatal
    else
        /home/alex/.mc-venv/bin/python3 src/tests/run_streaming_plan_classification_cleanup.py \
            --binary build/motioncorr_streaming_plan_fault --root "$ROOT/after"
        /home/alex/.mc-venv/bin/python3 src/tests/run_early_streaming_oom.py \
            --binary build/motioncorr_faultinject --root "$ROOT/early"
    fi
    "$MC_D3_SAMPLE_GUARD" post "$ROOT/$mode-final"
    ;;
*) exit 2 ;;
esac
