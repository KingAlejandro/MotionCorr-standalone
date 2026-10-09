#!/bin/bash
# usage: build.sh <src> <build> [extra cmake args]
set -u
src=$1; bld=$2; shift 2
NV=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
cmake -S $src -B $bld -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python "$@" > $bld.cfg.log 2>&1
rc=$?; [ $rc -ne 0 ] && { echo "CFG FAIL $rc"; exit $rc; }
flock /tmp/motioncorr-build.lock taskset -c 104-118 nice -n 5 cmake --build $bld -j15 > $bld.build.log 2>&1
rc=$?; echo "BUILD $bld rc=$rc"; exit $rc
