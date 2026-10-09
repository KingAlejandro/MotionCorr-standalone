#!/bin/bash
# Compiled negative controls on the composed tree (c0f82c2). Each mutant must make its test FAIL.
set -u
R=/home/alex/mc-rc; S=$R/src-mut; B=$R/build-mut; L=$R/mutants.log
: > $L
$R/build.sh $S $B -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive >> $L 2>&1 || { echo "BASE BUILD FAIL" >> $L; exit 1; }
mut() { # name file sed-expr test
  local name=$1 f=$2 expr=$3 t=$4
  git -C $S checkout -q -- .
  sed -i "$expr" $S/$f
  if git -C $S diff --quiet; then echo "$name: SED DID NOT APPLY" >> $L; return; fi
  git -C $S diff --stat | tail -1 >> $L
  flock /tmp/motioncorr-build.lock taskset -c 104-118 nice -n 5 cmake --build $B -j15 > $B.mut-$name.log 2>&1
  local brc=$?
  if [ $brc -ne 0 ]; then echo "$name: BUILD FAIL rc=$brc" >> $L; return; fi
  (cd $B && env CUDA_VISIBLE_DEVICES=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d taskset -c 64-71 ctest -R "^$t\$" --output-on-failure --timeout 900 > $B.ctest-$name.log 2>&1)
  local trc=$?
  echo "$name: test $t rc=$trc ($( [ $trc -ne 0 ] && echo DETECTED || echo SURVIVED ))" >> $L
  grep -m3 "FAIL\|must\|mismatch" $B.ctest-$name.log | sed "s/^/    /" >> $L
}
mut fbp_retain_unrequested src/frame_buffer_pool.cpp "111s/on \&\& reusable \&\& free_list/on \&\& free_list/" FrameBufferPool
mut fbp_no_inplace_keep    src/frame_buffer_pool.cpp "63s/(size_t)array.nzyxdimAlloc == elements)/false)/" FrameBufferPool
mut spt_no_owner_check     src/stage_profile.cpp "220s/!onOwner() || //;230s/!onOwner() || //" StageProfileThreads
mut c_per_frame_fft_wait   src/acc/cuda/cuda_movie_session.cu "1879a\\        HANDLE_ERROR(cudaDeviceSynchronize());" CudaDoseNormalization
mut b_skip_adler           src/acc/cuda/cuda_movie_session.cu "1757s/if (hs\[j\].adler/if (false \&\& hs[j].adler/" CudaNvcompAcceptanceFailures
mut b_spread_wrong_src     src/acc/cuda/cuda_deflate_layout.h "209s/lead + packed;/packed;/" DeflateLayout
git -C $S checkout -q -- .
echo MUTANTS_DONE >> $L
