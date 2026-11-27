#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
mkdir -p "$S/src-fix" "$S/logs"
tar -xf /mnt/clathrin/mc-peakfit-src.tar -C "$S/src-fix"
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export TMPDIR=$S/tmp
mkdir -p "$TMPDIR"
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
exec 8>/tmp/motioncorr-bench.lock
flock -s 8
exec 9>/tmp/motioncorr-build.lock
flock 9
{ date -u; hostname; nvidia-smi -L; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv; taskset -cp $$; df -h "$S"; cmake --version; g++ --version; nvcc --version; sha256sum /mnt/clathrin/mc-peakfit-src.tar; } > "$S/logs/host.txt"
for cfg in cpu cuda nvcomp; do
 args=(-DCUDA=OFF)
 if [ "$cfg" != cpu ]; then args=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=OFF); fi
 if [ "$cfg" = nvcomp ]; then args+=(-DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive); fi
 set +e
 taskset -c 96-103 cmake -S "$S/src-fix" -B "$S/build-$cfg" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 "${args[@]}" > "$S/logs/configure-$cfg.log" 2>&1
 rc=$?; echo "$rc" > "$S/logs/configure-$cfg.exit"
 if [ "$rc" = 0 ]; then taskset -c 96-103 cmake --build "$S/build-$cfg" -j8 > "$S/logs/build-$cfg.log" 2>&1; rc=$?; echo "$rc" > "$S/logs/build-$cfg.exit"; fi
 set -e
 echo "$cfg build=$rc $(date -u +%FT%TZ)" >> "$S/logs/progress.txt"
 [ "$rc" = 0 ] || exit "$rc"
 # Hold this GPU lock for the entire suite, select by UUID, eight host CPUs.
 exec 7>/tmp/motioncorr-gpu0-correctness.lock
 flock 7
 export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
 nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv >> "$S/logs/occupancy-$cfg.txt"
 set +e
 taskset -c 96-103 ctest --test-dir "$S/build-$cfg" --output-on-failure --output-junit "$S/logs/ctest-$cfg.xml" -j1 > "$S/logs/ctest-$cfg.log" 2>&1
 rc=$?; echo "$rc" > "$S/logs/ctest-$cfg.exit"
 set -e
 flock -u 7
 echo "$cfg ctest=$rc $(date -u +%FT%TZ)" >> "$S/logs/progress.txt"
done
echo DONE >> "$S/logs/progress.txt"
