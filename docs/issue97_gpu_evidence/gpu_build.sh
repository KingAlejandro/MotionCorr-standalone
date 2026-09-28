#!/bin/bash
# Issue #97 CUDA build on 4GPUs (shared box, fallback per COMMON.md).
# BUILD_TESTING is OFF deliberately: main now hard-requires python3 + numpy for
# BUILD_TESTING=ON, and this host has no numpy, so ON would FATAL_ERROR at configure.
set -u
ROOT=/home/alex/mc-issue97-gpu
BASE_SHA=8323c55faf1c4ddbe35dd36c5cd1266d48f25c38
FIXED_SHA=95c0cfb86e967ed25bed3fdd7ea8e5cf882f5971
REPO=https://github.com/KingAlejandro/MotionCorr-standalone.git
export PATH=/usr/local/cuda-12.8/bin:$PATH
LANE="taskset -c 96-103"      # COMMON.md: 4GPUs is capped at 8 logical CPUs
J=8

mkdir -p "$ROOT"; rm -rf "$ROOT/build-base" "$ROOT/build-fixed"; exec >"$ROOT/build.log" 2>&1
echo "############ GPU BUILD START $(date -Is) ############"
echo "--- host / toolchain ---"; hostname; nvcc --version | tail -2
nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader
echo "--- lane ---"; $LANE bash -c 'grep Cpus_allowed_list /proc/self/status'
echo "--- numpy present? (expect NO; why BUILD_TESTING is OFF) ---"
python3 -c 'import numpy' 2>&1 | tail -1

for pair in "base:$BASE_SHA" "fixed:$FIXED_SHA"; do
    name=${pair%%:*}; sha=${pair##*:}
    d=$ROOT/src-$name; b=$ROOT/build-$name
    [ -d "$d/.git" ] || { rm -rf "$d"; git clone -q "$REPO" "$d"; }
    git -C "$d" fetch -q origin
    git -C "$d" checkout -q --detach "$sha" || { echo "checkout $sha FAILED"; exit 92; }
    echo "[$name] HEAD=$(git -C "$d" rev-parse HEAD) dirty=$(git -C "$d" status --porcelain | wc -l)"
    sha256sum "$d/src/motioncorr_runner.cpp"
    rm -rf "$b"; mkdir -p "$b"
    # A100 is sm_80. The project's `if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)` guard does not
    # fire under CMake 3.28 (enable_language(CUDA) already defines it), leaving the target with
    # an empty CUDA_ARCHITECTURES and failing the generate step -- so set it explicitly.
    $LANE cmake -S "$d" -B "$b" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DBUILD_TESTING=OFF \
          -DCMAKE_CUDA_ARCHITECTURES=80 > "$ROOT/configure-$name.log" 2>&1
    rc=$?
    echo "[$name] configure exit=$rc"
    if [ $rc -ne 0 ]; then
        echo "[$name] CONFIGURE FAILED -- refusing to build or run. Tail:"
        tail -6 "$ROOT/configure-$name.log"
        echo "STATUS=CONFIGURE_FAILED"
        exit 91
    fi
    grep -E "^CMAKE_BUILD_TYPE|^CUDA:BOOL|^CMAKE_CUDA_ARCHITECTURES" "$b/CMakeCache.txt" 2>/dev/null
    $LANE cmake --build "$b" -j $J > "$ROOT/build-$name.out" 2>&1
    rc=$?
    echo "[$name] build exit=$rc"
    if [ $rc -ne 0 ]; then echo "[$name] BUILD FAILED"; tail -15 "$ROOT/build-$name.out"; echo "STATUS=BUILD_FAILED"; exit 93; fi
    echo "[$name] binary: $(sha256sum "$b/motioncorr" 2>/dev/null || echo MISSING)"
    echo "[$name] links cudart? $(ldd "$b/motioncorr" 2>/dev/null | grep -c cudart)"
done
echo "STATUS=BUILD_DONE"
echo "############ GPU BUILD END $(date -Is) ############"
