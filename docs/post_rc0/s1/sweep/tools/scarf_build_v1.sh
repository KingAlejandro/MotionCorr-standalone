#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Submit on CPU partition; immutable after checksum verification.
set -u
W=$HOME/mc-post-rc0-s1
export TMPDIR=/tmp
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH=$CU/bin:$PATH
mkdir -p "$W/build-records"
trap 'rc=$?; echo "$rc" > "$W/build.exit"' EXIT
hostname > "$W/build-records/host.txt"
lscpu >> "$W/build-records/host.txt"
env | sort > "$W/build-records/environment.txt"
for sha in F e875d5fe f6c41e24 8477dc1b d01f512d; do
  mkdir -p "$W/src-$sha"
  tar -xzf "$W/archives/$sha.tar.gz" -C "$W/src-$sha" || exit $?
  sha256sum "$W/archives/$sha.tar.gz" >> "$W/build-records/archives.sha256"
  for cfg in cpu cuda; do
    opts=(-DCUDA=OFF)
    if [ "$cfg" = cuda ]; then
      opts=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=$CU/bin/nvcc -DCUDAToolkit_ROOT=$CU -DUSE_NVCOMP=OFF)
      if [ "$sha" = F ]; then opts+=(-DUSE_NVCOMP=ON -DNVCOMP_ROOT=$HOME/nvcomp-sdk); fi
    fi
    cmd=(cmake -S "$W/src-$sha" -B "$W/build-$sha-$cfg" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF "${opts[@]}")
    printf '%q ' "${cmd[@]}" >> "$W/build-records/commands.log"; echo >> "$W/build-records/commands.log"
    "${cmd[@]}" > "$W/build-records/configure-$sha-$cfg.log" 2>&1
    rc=$?; echo "configure $sha $cfg rc=$rc" >> "$W/build-records/status.log"
    [ "$rc" = 0 ] || exit "$rc"
    cmd=(cmake --build "$W/build-$sha-$cfg" -j8)
    printf '%q ' "${cmd[@]}" >> "$W/build-records/commands.log"; echo >> "$W/build-records/commands.log"
    "${cmd[@]}" > "$W/build-records/build-$sha-$cfg.log" 2>&1
    rc=$?; echo "build $sha $cfg rc=$rc" >> "$W/build-records/status.log"
    [ "$rc" = 0 ] || exit "$rc"
    sha256sum "$W/build-$sha-$cfg/motioncorr" >> "$W/build-records/binaries.sha256"
    cp "$W/build-$sha-$cfg/CMakeCache.txt" "$W/build-records/cache-$sha-$cfg.txt"
    cp "$W/build-$sha-$cfg/CMakeFiles/motioncorr_core.dir/flags.make" "$W/build-records/flags-$sha-$cfg.make"
  done
done
