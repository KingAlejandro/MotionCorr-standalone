#!/bin/bash
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-D10d
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
cd "$W"
ASAN=(-DCMAKE_BUILD_TYPE=RelWithDebInfo '-DCMAKE_CXX_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer' '-DCMAKE_C_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer' -DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined)
CUDA=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8)
build() {
 name=$1; src=$2; mask=$3; shift 3
 echo "START $name $(date -u +%FT%TZ)"
 taskset -c "$mask" cmake -S "$src" -B "build-$name" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 "$@" >"logs/configure-$name.log" 2>&1
 taskset -c "$mask" cmake --build "build-$name" -j8 >"logs/build-$name.log" 2>&1
 rc=$?
 echo "DONE $name rc=$rc $(date -u +%FT%TZ)"
}
case $1 in
 a) build head-cpu src-head 112-119 -DCUDA=OFF; build base-cpu src-base 112-119 -DCUDA=OFF; build m2-cpu src-m2 112-119 -DCUDA=OFF; build composed-cpu src-composed 112-119 -DCUDA=OFF ;;
 b) build head-asan src-head 80-87 -DCUDA=OFF "${ASAN[@]}"; build head-cuda src-head 80-87 "${CUDA[@]}" -DUSE_NVCOMP=OFF; build head-nvcomp src-head 80-87 "${CUDA[@]}" -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive ;;
esac
