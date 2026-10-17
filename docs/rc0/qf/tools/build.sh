#!/bin/bash
# QF-prep builds of the exact SHA: CPU, CUDA sm80, CUDA sm80 + nvCOMP. CPUs 96-103, -j8.
# Gated on the bench lock (probe only, poll 60 s). Abort on any non-zero rc.
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-QF-PREP
SRC=$W/src
SHA=${QF_SHA:-483e881d9a6a352dba3268dac0f8c729364860b5}
CPUS=${QF_CPUS:-96-103}
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
mkdir -p $W/logs
cd $SRC || exit 90
[ "$(git rev-parse HEAD)" = "$SHA" ] || exit 91
[ "$(git status --porcelain | wc -l)" = 0 ] || exit 92
until flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held, waiting $(date -u +%T)"; sleep 60; done
build() { # name extra...
  name=$1; shift
  echo "=== configure $name $(date -u +%FT%TZ)"
  taskset -c $CPUS cmake -S $SRC -B $W/build-$name -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$PY "$@" > $W/logs/configure-$name.log 2>&1
  rc=$?; echo "configure $name rc=$rc"; [ $rc -eq 0 ] || return $rc
  grep CMAKE_HOME_DIRECTORY $W/build-$name/CMakeCache.txt
  echo "=== build $name $(date -u +%FT%TZ)"
  taskset -c $CPUS cmake --build $W/build-$name -j8 > $W/logs/build-$name.log 2>&1
  rc=$?; echo "build $name rc=$rc $(date -u +%FT%TZ)"
  [ $rc -eq 0 ] && sha256sum $W/build-$name/motioncorr && grep -h -- '-O3' $W/build-$name/CMakeFiles/motioncorr.dir/flags.make | head -1
  return $rc
}
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8"
build cpu -DBUILD_TESTING=ON -DCUDA=OFF || exit 1
build cuda -DBUILD_TESTING=ON $CUDA_ARGS -DUSE_NVCOMP=OFF || exit 2
build nvcomp -DBUILD_TESTING=ON $CUDA_ARGS -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC || exit 3
for n in cpu cuda nvcomp; do echo "ctest -N $n: $(ctest --test-dir $W/build-$n -N | tail -1)"; done
echo ALL_BUILDS_DONE
