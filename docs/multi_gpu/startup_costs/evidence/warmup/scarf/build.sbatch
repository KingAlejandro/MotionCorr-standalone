#!/bin/bash
#SBATCH -p scarf
#SBATCH --cpus-per-task=16
#SBATCH -t 02:00:00
#SBATCH -J mcwarm-build
#SBATCH -o /home/vol05/scarf1415/mc-warmup-20261014/build-%j.out
set -uo pipefail
D=/home/vol05/scarf1415/mc-warmup-20261014
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}"
export TMPDIR=/tmp
cd "$D"
echo "=== VENUE ==="; date -Is; hostname; nvcc --version|tail -1; gs --version
B() {
  local n=$1
  rm -rf build-$n
  cmake -S src-$n -B build-$n -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" \
    -DCUDAToolkit_ROOT="$CUDA_HOME" > conf-$n.log 2>&1; local c=$?
  cmake --build build-$n --parallel 16 > build-$n.log 2>&1; local r=$?
  echo "$n: configure=$c build=$r"
  [ $r -ne 0 ] && grep -iE "error" build-$n.log | head -10
  grep CMAKE_HOME_DIRECTORY build-$n/CMakeCache.txt
}
B cand
echo "=== BINARIES ==="
sha256sum build-base/motioncorr build-cand/motioncorr
echo BUILD_DONE
