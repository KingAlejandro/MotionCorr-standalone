#!/bin/bash
set -u
S=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
PY=/home/alex/.mc-venv/bin/python3
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
[ -d $S/src-diag2 ] || git clone -q --no-checkout /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/src $S/src-diag2 || exit 90
git -C $S/src-diag2 checkout -q 1db869025507ac801845b4001b84e6bc0e77a645 || exit 91
git -C $S/src-diag2 apply $S/tools/diag_s1_patch_dump_drop.diff || exit 92
git -C $S/src-diag2 apply $S/tools/diag_s1_r1_ccf_ties.diff || exit 93
echo "src-diag2 HEAD $(git -C $S/src-diag2 rev-parse HEAD) modified: $(git -C $S/src-diag2 status --short | tr "\n" " ")"
build() { name=$1; src=$2; shift 2
  while ! flock -n /tmp/motioncorr-bench.lock true; do sleep 30; done
  taskset -c 104-111 cmake -S $src -B $S/build-$name -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$PY -DBUILD_TESTING=OFF "$@" > $S/logs/configure-$name.log 2>&1 || { echo "configure $name FAILED"; return 1; }
  taskset -c 104-111 cmake --build $S/build-$name -j8 --target motioncorr > $S/logs/build-$name.log 2>&1; rc=$?
  echo "build $name rc=$rc $(date -u +%FT%TZ) $(grep -E "^CXX_FLAGS" $S/build-$name/CMakeFiles/motioncorr.dir/flags.make 2>/dev/null | head -1)"
  [ $rc -eq 0 ] && sha256sum $S/build-$name/motioncorr; return $rc
}
CU="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC"
build diag2-cpu $S/src-diag2 -DCUDA=OFF || tail -30 $S/logs/build-diag2-cpu.log
build diag2-nvcomp $S/src-diag2 $CU || grep -m20 -E "error" $S/logs/build-diag2-nvcomp.log
echo BUILDS-R1-DONE
