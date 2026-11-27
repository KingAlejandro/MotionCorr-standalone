#!/bin/bash
# S1.3c-null build (diag5, CUDA+nvCOMP only): adds MC_DIAG_NULL_ROWS to diag4,
# identical CMake options. Sources were copied with `git archive`.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
CPUS=${CPUS:-104-111}
build() { name=$1; src=$2; shift 2
  while ! flock -s -n /tmp/motioncorr-bench.lock true; do sleep 60; done  # shared probe: defer to exclusive (benchmark) holders only
  taskset -c $CPUS cmake -S $src -B $S/build-$name -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$PY -DBUILD_TESTING=OFF "$@" > $S/logs/configure-$name.log 2>&1 || { echo "configure $name FAILED"; return 1; }
  taskset -c $CPUS cmake --build $S/build-$name -j8 --target motioncorr > $S/logs/build-$name.log 2>&1; rc=$?
  echo "build $name rc=$rc $(date -u +%FT%TZ) $(grep -E "^CXX_FLAGS" $S/build-$name/CMakeFiles/motioncorr.dir/flags.make 2>/dev/null | head -1)"
  [ $rc -eq 0 ] && sha256sum $S/build-$name/motioncorr; return $rc
}
CU="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC"
st=0



build diag5-nvcomp $S/src-diag5 $CU || { st=1; grep -m20 error $S/logs/build-diag5-nvcomp.log; }
echo BUILDS-DONE st=$st
exit $st
