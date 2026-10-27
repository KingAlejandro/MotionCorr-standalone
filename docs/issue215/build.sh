#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-215
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
cd "$W/src"
for cfg in nvcomp cuda cpu; do
  opts=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3)
  if [ "$cfg" = cpu ]; then opts+=(-DCUDA=OFF); else opts+=(-DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=80); fi
  if [ "$cfg" = nvcomp ]; then opts+=(-DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive); else opts+=(-DUSE_NVCOMP=OFF); fi
  taskset -c 64-71 cmake -S . -B "$W/build-$cfg" "${opts[@]}" > "$W/config-$cfg.log" 2>&1
  taskset -c 64-71 cmake --build "$W/build-$cfg" -j8 > "$W/build-$cfg.log" 2>&1
  echo "build $cfg rc=0"
done
