#!/bin/bash
# QF builds of the exact SHA: CPU, CUDA sm80, CUDA sm80 + nvCOMP, -j8 on $QF_CPUS, into $QF_W/build-*.
# Required: QF_W (holds src/, a git checkout of the frozen SHA), QF_SHA (the frozen SHA), QF_CPUS.
# Gated on the bench lock (probe only, poll 60 s). Abort on any non-zero rc.
set -u
: "${QF_W:?set QF_W to the QF workspace}" "${QF_SHA:?set QF_SHA to the frozen SHA}" "${QF_CPUS:?set QF_CPUS}"
W=$QF_W
SRC=$W/src
SHA=$QF_SHA
CPUS=$QF_CPUS
export PATH=/home/vol05/scarf1415/mc-rc0-scarfF/venv/bin:/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0/bin:$PATH
PY=/home/vol05/scarf1415/mc-rc0-scarfF/venv/bin/python3
NVC=/home/vol05/scarf1415/nvcomp-sdk
cd $SRC || { echo "no source checkout at $SRC"; exit 90; }
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "HEAD $(git rev-parse HEAD) != QF_SHA $SHA"; exit 91; }
[ "$(git status --porcelain | wc -l)" = 0 ] || { echo "source tree not clean"; git status --porcelain; exit 92; }
mkdir -p $W/logs
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
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0/bin/nvcc -DCUDAToolkit_ROOT=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0"
build cpu -DBUILD_TESTING=ON -DCUDA=OFF || exit 1
build cuda -DBUILD_TESTING=ON $CUDA_ARGS -DUSE_NVCOMP=OFF || exit 2
build nvcomp -DBUILD_TESTING=ON $CUDA_ARGS -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC || exit 3
for n in cpu cuda nvcomp; do echo "ctest -N $n: $(ctest --test-dir $W/build-$n -N | tail -1)"; done
echo ALL_BUILDS_DONE
