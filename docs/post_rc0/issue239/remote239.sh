#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-hygiene239
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
cd "$W/src"
[ "$(git rev-parse HEAD)" = 1c14e8882b4754903da4499f1ceca5fd8037f630 ]
[ -z "$(git status --porcelain)" ]
mkdir -p "$W/logs"
{ date -u; hostname; uname -a; g++ --version; nvcc --version; nvidia-smi; taskset -c 112-119 true; git rev-parse HEAD; } > "$W/logs/build-info.txt"
for cfg in cpu cuda nvcomp; do
  flock -n /tmp/motioncorr-bench.lock true
  opts=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3)
  if [ "$cfg" = cpu ]; then opts+=(-DCUDA=OFF); else opts+=(-DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=80); fi
  if [ "$cfg" = nvcomp ]; then opts+=(-DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive); else opts+=(-DUSE_NVCOMP=OFF); fi
  taskset -c 112-119 cmake -S . -B "$W/build-$cfg" "${opts[@]}" > "$W/logs/configure-$cfg.log" 2>&1
  echo "configure $cfg rc=0"
  taskset -c 112-119 cmake --build "$W/build-$cfg" -j8 > "$W/logs/build-$cfg.log" 2>&1
  echo "build $cfg rc=0"
  sha256sum "$W/build-$cfg/motioncorr" > "$W/logs/binary-$cfg.sha256"
done
