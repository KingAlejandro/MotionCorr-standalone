#!/usr/bin/env bash
# round96 correctness-foundation -- fresh CUDA compilation on the shared 4-GPU VM.
# COMPILE ONLY. No CUDA context is created; nothing is executed on a GPU.
# Lane: taskset -c 96-111 (16 logical CPUs, NUMA node1), build -j8,
#       serialized under /tmp/motioncorr-bench.lock.
set -uo pipefail
ROOT=/home/alex/mc-i96-cuda
BUNDLE=/home/alex/mc-i96-integration.bundle
export PATH=/usr/local/cuda/bin:$PATH
rm -rf "$ROOT"; mkdir -p "$ROOT"
LOG=$ROOT/logs; mkdir -p "$LOG"
exec > >(tee -a "$LOG/cuda_compile.log") 2>&1

echo "##### PROVENANCE #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
numactl --show | grep -E "physcpubind|membind|nodebind"
echo "--- lscpu node/socket/core for the 96-111 lane ---"
lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#' | awk -F, '$1>=96 && $1<=111'
echo "Thread(s) per core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}')"
echo "--- devices present (NOT used: compile only) ---"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
echo "--- compute apps at start ---"; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = none)"
echo "--- toolchain ---"; nvcc --version | tail -2; g++ --version | head -1; cmake --version | head -1
echo "--- load ---"; cat /proc/loadavg

echo; echo "##### SOURCE #####"
sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" "$ROOT/src"
cd "$ROOT/src"
echo "candidate head: $(git rev-parse HEAD)"
echo "tree: $(git rev-parse HEAD^{tree})"
git status --porcelain | head

echo; echo "##### ARM 1: DEFAULT CUDA CONFIGURE (no -DCMAKE_CUDA_ARCHITECTURES) #####"
echo "Tests the #26-reported CMakeLists.txt:59 fallback guard on this exact tree."
cmake -S . -B build-default -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DBUILD_TESTING=OFF > "$LOG/arm1-configure.log" 2>&1
A1=$?
echo "arm1 configure exit=$A1"
tail -12 "$LOG/arm1-configure.log"
if [ $A1 -eq 0 ]; then
  cmake --build build-default -j8 > "$LOG/arm1-build.log" 2>&1
  echo "arm1 build exit=$?"
  echo "arm1 compile errors: $(grep -cE 'error:' "$LOG/arm1-build.log")"
else
  echo "arm1 build: NOT ATTEMPTED (configure failed)"
fi

echo; echo "##### ARM 2: EXPLICIT sm80 #####"
cmake -S . -B build-sm80 -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON > "$LOG/arm2-configure.log" 2>&1
A2=$?
echo "arm2 configure exit=$A2"
tail -6 "$LOG/arm2-configure.log"
grep -E "CMAKE_BUILD_TYPE|CMAKE_CUDA_ARCHITECTURES|^CUDA:" build-sm80/CMakeCache.txt 2>/dev/null | head
cmake --build build-sm80 -j8 > "$LOG/arm2-build.log" 2>&1
A2B=$?
echo "arm2 build exit=$A2B"
echo "arm2 compile errors: $(grep -cE 'error:' "$LOG/arm2-build.log")"
echo "arm2 warnings in integrated files:"
grep -nE "warning:" "$LOG/arm2-build.log" | grep -E "image\.h|rwMRC\.h|rwTIFF\.h|micrograph_model|motioncorr_runner" | head -10 || echo "  (none in src/image.h, src/rwMRC.h, src/rwTIFF.h, src/micrograph_model.cpp, src/motioncorr_runner.cpp)"
echo "--- binaries ---"
ls -l build-sm80/motioncorr 2>/dev/null
sha256sum build-sm80/motioncorr 2>/dev/null
echo "--- CUDA actually linked in? ---"
ldd build-sm80/motioncorr 2>/dev/null | grep -iE "cudart|cufft" || echo "  (no CUDA runtime linked -- would mean CUDA=ON did not take effect)"
echo "--- device code architectures embedded ---"
cuobjdump --list-elf build-sm80/motioncorr 2>/dev/null | head -5 || echo "  (cuobjdump unavailable)"

echo; echo "##### NO GPU EXECUTION PERFORMED #####"
echo "compute apps at end:"; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = nothing ran on a device)"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
