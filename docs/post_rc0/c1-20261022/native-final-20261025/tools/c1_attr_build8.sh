#!/bin/bash
# i8 K269 attribution builds (plain CUDA, Release, target motioncorr only, -j8 on the granted CPUs 96-103, nonblocking shared build lock).
# usage: c1_attr_build8.sh n254_260|N21093
#   n254_260  = C1 merge commit 3d560a16 (numerics #254+#260 on main 3691374 plus the #267/#269/#272 tooling, no #270, no D2/D3, no independent fixes)
#   N21093    = C1 merge commit 21093fe9 (adds #270; the N arm of T24)
# Sources are exported with `git archive` from the tested checkout's history (read only).
set -u
D=$(cd "$(dirname "$0")" && pwd); source "$D/c1_env.sh" || exit 1
arm=$1; A=$C1_SCR/attr/$arm
case $arm in n254_260) rev=3d560a16;; N21093) rev=21093fe9;; *) echo unknown; exit 2;; esac
exec 8>>"$C1_BUILD_LOCK"; flock -n 8 || { echo "build lock contended; stopping, no retry"; exit 5; }
[ ! -e "$A" ] || { echo "$A exists; refusing"; exit 4; }
mkdir -p $A/src
full=$(git -C $C1_BUILDS_SRC/src rev-parse $rev^{commit}) || exit 4
git -C $C1_BUILDS_SRC/src archive $full | tar -x -C $A/src || exit 4
echo $full > $A/SOURCE
(cd $A/src && find . -type f -print0 | sort -z | xargs -0 sha256sum) > $A/source-files.sha256
CUDA_ARGS="-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8"
taskset -c $C1_CPUS cmake -S $A/src -B $A/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$C1_PY -DMC_REQUIRE_ALL_DECODERS=ON $CUDA_ARGS -DUSE_NVCOMP=OFF -DBUILD_TESTING=OFF > $A/configure.log 2>&1 || { echo "configure rc=$?"; exit 3; }
taskset -c $C1_CPUS cmake --build $A/build --target motioncorr --parallel 8 > $A/build.log 2>&1; rc=$?
echo "build rc=$rc source $full"
[ $rc -eq 0 ] && { sha256sum $A/build/motioncorr | tee $A/binary.sha256; grep -h -- '-O3' $A/build/CMakeFiles/motioncorr.dir/flags.make | head -1; }
exit $rc
