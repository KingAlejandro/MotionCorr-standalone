#!/usr/bin/env bash
# round96 -- CUDA compile, corrected arms. COMPILE ONLY, no GPU execution.
set -uo pipefail
ROOT=/home/alex/mc-i96-cuda
export PATH=/usr/local/cuda/bin:$PATH
LOG=$ROOT/logs
exec > >(tee -a "$LOG/cuda_compile2.log") 2>&1
echo "##### CUDA COMPILE, CORRECTED ARMS #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
grep -E "Cpus_allowed_list" /proc/self/status
cd "$ROOT/src"; echo "head: $(git rev-parse HEAD)"

echo
echo "##### ARM 2: explicit sm80, BUILD_TESTING=OFF (product CUDA compile) #####"
rm -rf build-sm80
cmake -S . -B build-sm80 -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF > "$LOG/arm2-configure.log" 2>&1
echo "arm2 configure exit=$?"; tail -4 "$LOG/arm2-configure.log"
grep -E "^CMAKE_BUILD_TYPE|^CMAKE_CUDA_ARCHITECTURES|^CUDA:" build-sm80/CMakeCache.txt
cmake --build build-sm80 -j8 > "$LOG/arm2-build.log" 2>&1
echo "arm2 build exit=$?"
echo "arm2 compile errors: $(grep -cE 'error:' "$LOG/arm2-build.log")"
echo "arm2 warnings in the integrated files:"
grep -nE "warning:" "$LOG/arm2-build.log" | grep -E "image\.h|rwMRC\.h|rwTIFF\.h|micrograph_model|motioncorr_runner" | head -10 || echo "  (none)"
ls -l build-sm80/motioncorr 2>/dev/null; sha256sum build-sm80/motioncorr 2>/dev/null
echo "--- CUDA runtime actually linked? ---"
ldd build-sm80/motioncorr 2>/dev/null | grep -iE "cudart|cufft" || echo "  !! no CUDA runtime linked"
echo "--- device code architectures actually embedded ---"
cuobjdump --list-elf build-sm80/motioncorr 2>/dev/null | head -4 || \
  nvdisasm -h >/dev/null 2>&1 && cuobjdump --list-elf build-sm80/motioncorr 2>&1 | head -4 || echo "  (cuobjdump not on PATH)"
/usr/local/cuda/bin/cuobjdump --list-elf build-sm80/motioncorr 2>/dev/null | head -4

echo
echo "##### ARM 3: explicit sm80, BUILD_TESTING=ON with a numpy-providing python #####"
echo "Records the new #72 numpy requirement's effect on a CUDA host."
VENV=/home/alex/.mc-i96-venv
if [ ! -x "$VENV/bin/python3" ]; then
  python3 -m venv "$VENV" > "$LOG/venv.log" 2>&1
  "$VENV/bin/pip" -q install numpy >> "$LOG/venv.log" 2>&1
fi
"$VENV/bin/python3" -c "import numpy;print('venv numpy', numpy.__version__)" || echo "venv numpy unavailable"
rm -rf build-sm80-tests
cmake -S . -B build-sm80-tests -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
      -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$VENV/bin/python3" > "$LOG/arm3-configure.log" 2>&1
echo "arm3 configure exit=$?"; tail -4 "$LOG/arm3-configure.log"
cmake --build build-sm80-tests -j8 > "$LOG/arm3-build.log" 2>&1
echo "arm3 build exit=$?"
echo "arm3 compile errors: $(grep -cE 'error:' "$LOG/arm3-build.log")"
echo "--- CUDA test target built? ---"
ls -l build-sm80-tests/cuda_wrapper_upload_failure 2>/dev/null || echo "  (not built)"
echo "--- collected tests in the CUDA configuration ---"
( cd build-sm80-tests && ctest --show-only=json-v1 2>/dev/null | "$VENV/bin/python3" -c "import json,sys;d=json.load(sys.stdin);ns=[t['name'] for t in d['tests']];print(len(ns));[print(' ',n) for n in ns]" )
echo "--- required-inventory check under the CUDA configuration ---"
"$VENV/bin/python3" tools/validate_test_collection.py --test-dir build-sm80-tests 2>&1 | tail -6
echo "validate exit=$?"

echo
echo "##### NO GPU EXECUTION #####"
nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = nothing ran on a device)"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
