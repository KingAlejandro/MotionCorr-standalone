#!/bin/bash
# Build the genuine nvCOMP-ingest fault binary out of tree: the tested build's run_motioncorr.cpp.o and libmotioncorr_core.a (d7c4e2e3 build of e77a51a2, read in place)
# plus the test-only interposer; no CMake or production-source change. The link line is build-nvcomp's link.txt, required to match its exact known prefix, with -rdynamic,
# --wrap=cudaLaunchKernel and the interposer object added and the output redirected to the fresh i8 scratch. The tested binary's hash is checked before and after.
# usage: c1_ingest_build.sh   (compiles one .cu file: build lock taken nonblocking)
set -u
D=$(cd "$(dirname "$0")" && pwd); source "$D/c1_env.sh" || exit 1
exec 8>>$C1_BUILD_LOCK; flock -n 8 || { echo "build lock contended; stopping"; exit 5; }
NB=$C1_BUILDS_SRC/build-nvcomp; B=$C1_SCR/build-ingest-fault
TESTED=d7c4e2e3baa370defb5d3252cd0ca6e4d7ab57c9a1665037fa54d461a51b2e6d
[ -d "$NB" ] && [ -f "$NB/CMakeFiles/motioncorr.dir/link.txt" ] && [ -f "$NB/libmotioncorr_core.a" ] && [ -f "$NB/CMakeFiles/motioncorr.dir/src/apps/run_motioncorr.cpp.o" ] || { echo "tested build inputs missing"; exit 4; }
[ "$(sha256sum $NB/motioncorr | cut -c1-64)" = "$TESTED" ] || { echo "tested nvcomp binary hash differs from the recorded d7c4e2e3"; exit 4; }
# inputs pinned by hash (measured 2026-10-26 on 4GPUs, before the build): link line, core library, application object
sha256sum -c --status <<PIN || { echo "link inputs differ from their recorded hashes; refusing"; exit 4; }
d80b3602d5255d22ee9300f398a9c7332e706a03b7ff91606c5758cc99cda138  $NB/CMakeFiles/motioncorr.dir/link.txt
d6d78256e5120d60fdbc4129920229aab8efa1126bde1903cbe29d3fcfc394c8  $NB/libmotioncorr_core.a
2268fc4181773efc1b5b3b7778a698a652709ccc33728b51ceaac24f12b7df33  $NB/CMakeFiles/motioncorr.dir/src/apps/run_motioncorr.cpp.o
PIN
case "$B" in $C1_SCR/build-ingest-fault) ;; *) echo "output dir outside the i8 scratch"; exit 4;; esac
[ ! -e "$B" ] || { echo "$B already exists; refusing (stale outputs); new iteration = new scratch"; exit 4; }
mkdir "$B" || exit 4
sha256sum $NB/motioncorr $NB/libmotioncorr_core.a $NB/CMakeFiles/motioncorr.dir/src/apps/run_motioncorr.cpp.o $D/cuda_ingest_sticky_fault.cu > $B/inputs.sha256 || exit 4
nvcc -O3 -DNDEBUG -std=c++17 "--generate-code=arch=compute_80,code=[compute_80,sm_80]" -D_CUDA_ENABLED -D_NVCOMP_ENABLED \
  -I$C1_BUILDS_SRC/src -I$C1_NVCOMP/include -c $D/cuda_ingest_sticky_fault.cu -o $B/cuda_ingest_sticky_fault.o || exit 2
link=$(cat $NB/CMakeFiles/motioncorr.dir/link.txt) || exit 4
prefix='/usr/bin/c++ -O3 -DNDEBUG CMakeFiles/motioncorr.dir/src/apps/run_motioncorr.cpp.o -o motioncorr '
case "$link" in "$prefix"*) ;; *) echo "link.txt does not start with the expected prefix; refusing"; exit 4;; esac
rest=${link#"$prefix"}
read -ra rest_args <<< "$rest"
for w in "${rest_args[@]}"; do
  case "$w" in -o*|--output*) echo "unexpected output-like option in link.txt remainder: $w"; exit 4;; esac
done
args=(/usr/bin/c++ -O3 -DNDEBUG -rdynamic -Wl,--wrap=cudaLaunchKernel CMakeFiles/motioncorr.dir/src/apps/run_motioncorr.cpp.o "$B/cuda_ingest_sticky_fault.o" -o "$B/motioncorr_ingest_fault" "${rest_args[@]}")
printf '%q ' "${args[@]}" > $B/link.cmd
(cd $NB && "${args[@]}") || exit 3
[ -x $B/motioncorr_ingest_fault ] || exit 3
[ "$(sha256sum $NB/motioncorr | cut -c1-64)" = "$TESTED" ] || { echo "tested binary changed during the build"; exit 6; }
nm -D $B/motioncorr_ingest_fault | grep -q ' T __wrap_cudaLaunchKernel' || { echo "interposer symbol __wrap_cudaLaunchKernel not exported"; exit 7; }
sha256sum $B/motioncorr_ingest_fault > $B/binary.sha256; cat $B/binary.sha256
