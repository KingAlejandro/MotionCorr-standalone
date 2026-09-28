#!/usr/bin/env bash
# round96 correctness-foundation -- CUDA compile at the FINAL integrated head
# (all four groups incl. PR101). COMPILE ONLY; no CUDA context, no GPU execution.
set -uo pipefail
ROOT=/home/alex/mc-i96-cuda-final
BUNDLE=/home/alex/mc-i96-final.bundle
VENV=/home/alex/.mc-i96-venv
export PATH=/usr/local/cuda/bin:$PATH
rm -rf "$ROOT"; mkdir -p "$ROOT/logs"; LOG=$ROOT/logs
exec > >(tee -a "$LOG/cuda_final.log") 2>&1
echo "##### CUDA COMPILE AT FINAL HEAD #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
numactl --show | grep -E "physcpubind|membind|nodebind"
echo "lane node/socket/core:"; lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#' | awk -F, '$1>=96 && $1<=111' | head -4
echo "SMT thread(s)/core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}')"
echo "devices (not used):"; nvidia-smi --query-gpu=index,uuid,memory.used --format=csv,noheader
echo "compute apps at start:"; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = none)"
nvcc --version | tail -2; g++ --version|head -1; cmake --version|head -1
sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" "$ROOT/src"
cd "$ROOT/src"; echo "head: $(git rev-parse HEAD)"; echo "tree: $(git rev-parse HEAD^{tree})"

echo; echo "##### ARM 1: DEFAULT CUDA CONFIGURE (no -DCMAKE_CUDA_ARCHITECTURES) #####"
cmake -S . -B build-default -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DBUILD_TESTING=OFF > "$LOG/arm1.log" 2>&1
echo "arm1 configure exit=$?"
grep -A2 "CMake Error" "$LOG/arm1.log" | head -6

echo; echo "##### ARM 2: explicit sm80, BUILD_TESTING=OFF #####"
cmake -S . -B build-sm80 -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF > "$LOG/arm2c.log" 2>&1
echo "configure exit=$?"
cmake --build build-sm80 -j8 > "$LOG/arm2b.log" 2>&1
echo "build exit=$?  compile errors=$(grep -cE 'error:' "$LOG/arm2b.log")"
grep -nE "warning:" "$LOG/arm2b.log" | grep -E "image\.h|rwMRC\.h|rwTIFF\.h|micrograph_model|motioncorr_runner" | head || echo "no warnings in the five integrated source files"
sha256sum build-sm80/motioncorr
ldd build-sm80/motioncorr | grep -iE "cudart|cufft"
cuobjdump --list-elf build-sm80/motioncorr | sort -u | head -5

echo; echo "##### ARM 3: explicit sm80, BUILD_TESTING=ON #####"
cmake -S . -B build-tests -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
      -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$VENV/bin/python3" > "$LOG/arm3c.log" 2>&1
echo "configure exit=$?"
cmake --build build-tests -j8 > "$LOG/arm3b.log" 2>&1
echo "build exit=$?  compile errors=$(grep -cE 'error:' "$LOG/arm3b.log")"
echo "collected tests under CUDA=ON:"
( cd build-tests && ctest --show-only=json-v1 | "$VENV/bin/python3" -c "import json,sys;d=json.load(sys.stdin);ns=[t['name'] for t in d['tests']];print(len(ns));[print('  ',n) for n in ns]" )
"$VENV/bin/python3" tools/validate_test_collection.py --test-dir build-tests 2>&1 | tail -3
echo "validate exit=$?"
echo "device-free CTests only (no GPU execution attempted here):"
ls -l build-tests/cuda_wrapper_upload_failure build-tests/defect_parser build-tests/image_write_faults 2>/dev/null

echo; echo "##### NO GPU EXECUTION #####"
nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = nothing ran on a device)"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
