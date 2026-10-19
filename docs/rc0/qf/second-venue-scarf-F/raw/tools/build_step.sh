#!/bin/bash
source /home/vol05/scarf1415/mc-rc0-scarfF/tools/env.sh
cd $QF_W
bash tools/identity.sh > identity-build.txt 2>&1
bash tools/build_scarf.sh > logs/build.out 2>&1; rc=$?
echo "build_scarf.sh rc=$rc" >> logs/build.out
{
 echo "build_scarf.sh rc=$rc"
 for n in cpu cuda nvcomp; do
  echo "== $n"
  sha256sum build-$n/motioncorr build-$n/motioncorr_faultinject build-$n/motioncorr_resident_retry_fault 2>&1
  grep -E 'CXX_FLAGS|CUDA_FLAGS' build-$n/CMakeFiles/motioncorr.dir/flags.make
  grep -E '^(CMAKE_HOME_DIRECTORY|CMAKE_BUILD_TYPE|CUDA:BOOL|USE_NVCOMP|CMAKE_CUDA_ARCHITECTURES|Python3_EXECUTABLE|CMAKE_CXX_COMPILER:|CMAKE_CUDA_COMPILER:|NVCOMP)' build-$n/CMakeCache.txt
  grep -iE 'dose.symmetry|DOSE_SYMMETRY' logs/configure-$n.log
  grep -iE 'not found|WARNING' logs/configure-$n.log | head -5
  echo "ldd (LD_LIBRARY_PATH unset):"; env -u LD_LIBRARY_PATH ldd build-$n/motioncorr | grep -E 'not found|cufft|nvcomp|cudart|gomp|fftw|tiff|stdc'
  readelf -d build-$n/motioncorr | grep -E 'RPATH|RUNPATH'
  echo "ctest -N: $(ctest --test-dir build-$n -N | tail -1)"
 done
} > build-record.txt 2>&1
echo BUILD_STEP_DONE rc=$rc > build.sentinel
