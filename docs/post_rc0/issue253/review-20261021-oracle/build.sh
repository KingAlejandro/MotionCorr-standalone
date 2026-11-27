#!/bin/bash
# Release builds of the CPU, CUDA and CUDA+nvCOMP configurations; every step's exit code is recorded and checked.
set -eu
S=/mnt/clathrin/alex-motioncorr-254-oracle-20261021
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 CUDA_DEVICE_ORDER=PCI_BUS_ID
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
cu=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8)
run() { local label=$1; shift; set +e; taskset -c ${CPUS:-104-111} "$@" > "$S/logs/$label.log" 2>&1; local rc=$?; set -e; echo "$rc" > "$S/logs/$label.exit"; return "$rc"; }
for type in nvcomp cuda cpu; do
 opts=(-DCUDA=OFF)
 if [ "$type" = cuda ]; then opts=("${cu[@]}" -DUSE_NVCOMP=OFF); fi
 if [ "$type" = nvcomp ]; then opts=("${cu[@]}" -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive); fi
 run configure-$type cmake -S "$S/src" -B "$S/build-$type" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 "${opts[@]}"
 run build-$type cmake --build "$S/build-$type" -j8
done
echo done > "$S/build-done"
