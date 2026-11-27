#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export TMPDIR=$S/tmp
exec 8>/tmp/motioncorr-bench.lock
flock -s 8
for arm in A0 A1; do
 mkdir -p "$S/src-$arm"
 tar -xf /mnt/clathrin/mc-diag-$arm.tar -C "$S/src-$arm"
 set +e
 taskset -c 112-119 cmake -S "$S/src-$arm" -B "$S/build-$arm" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive > "$S/logs/configure-$arm.log" 2>&1
 rc=$?; echo "$rc" > "$S/logs/configure-$arm.exit"
 [ "$rc" = 0 ] || exit "$rc"
 taskset -c 112-119 cmake --build "$S/build-$arm" -j8 --target motioncorr > "$S/logs/build-$arm.log" 2>&1
 rc=$?; echo "$rc" > "$S/logs/build-$arm.exit"
 [ "$rc" = 0 ] || exit "$rc"
 set -e
 sha256sum "$S/build-$arm/motioncorr" >> "$S/logs/diag-binaries.sha256"
done
echo DONE > "$S/logs/diag-build.done"
