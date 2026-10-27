#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-254-review-20261021
mkdir -p "$S/src" "$S/logs"
tar -xf /mnt/clathrin/mc254-invariant.tar -C "$S/src"
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 CUDA_DEVICE_ORDER=PCI_BUS_ID
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
run() { local label=$1; shift; set +e; taskset -c 80-87 "$@" > "$S/logs/$label.log" 2>&1; local rc=$?; set -e; echo "$rc" > "$S/logs/$label.exit"; return "$rc"; }
cu=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8)
for type in nvcomp cuda cpu; do
 opts=(-DCUDA=OFF)
 if [ "$type" != cpu ]; then opts=("${cu[@]}" -DUSE_NVCOMP=OFF); fi
 if [ "$type" = nvcomp ]; then opts=("${cu[@]}" -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive); fi
 run configure-$type cmake -S "$S/src" -B "$S/build-$type" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 "${opts[@]}"
 run build-$type cmake --build "$S/build-$type" -j8
 # Acquire only for execution, release between suites. Never remove lock files.
 if [ "$type" != cpu ]; then
   exec 9>/tmp/motioncorr-gpu0-correctness.lock
   flock -w 60 9
   export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
   nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv > "$S/logs/occupancy-$type.log"
 fi
 run ctest-$type ctest --test-dir "$S/build-$type" -j1 --output-on-failure --output-junit "$S/logs/ctest-$type.xml" || true
 if [ "$type" != cpu ]; then flock -u 9; exec 9>&-; fi
done
echo done > "$S/done"
