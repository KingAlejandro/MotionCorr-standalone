#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Archives are produced with git archive, never macOS tar.
set -eu
W=/mnt/clathrin/alex-motioncorr-s1/sweep
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
mkdir -p "$W/build-records"
for sha in 6b6adf44 c499b1d3 2ff18e93; do
  mkdir -p "$W/src-$sha"
  tar -xzf "/mnt/clathrin/alex-motioncorr-s1/motioncorr-s1-$sha.tar.gz" -C "$W/src-$sha"
  sha256sum "/mnt/clathrin/alex-motioncorr-s1/motioncorr-s1-$sha.tar.gz" >> "$W/build-records/archives.sha256"
  for cfg in cpu cuda; do
    until flock -n /tmp/motioncorr-bench.lock true; do sleep 10; done
    opts=(-DCUDA=OFF)
    if [ "$cfg" = cuda ]; then
      opts=(-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=OFF)
    fi
    cmd=(taskset -c 96-103 cmake -S "$W/src-$sha" -B "$W/build-$sha-$cfg" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF "${opts[@]}")
    printf '%q ' "${cmd[@]}" >> "$W/build-records/commands.log"; echo >> "$W/build-records/commands.log"
    set +e
    "${cmd[@]}" > "$W/build-records/configure-$sha-$cfg.log" 2>&1
    rc=$?
    set -e
    echo "configure $sha $cfg rc=$rc" | tee -a "$W/build-records/status.log"
    [ "$rc" = 0 ] || exit "$rc"
    cmd=(taskset -c 96-103 cmake --build "$W/build-$sha-$cfg" -j8)
    printf '%q ' "${cmd[@]}" >> "$W/build-records/commands.log"; echo >> "$W/build-records/commands.log"
    set +e
    "${cmd[@]}" > "$W/build-records/build-$sha-$cfg.log" 2>&1
    rc=$?
    set -e
    echo "build $sha $cfg rc=$rc" | tee -a "$W/build-records/status.log"
    [ "$rc" = 0 ] || exit "$rc"
    sha256sum "$W/build-$sha-$cfg/motioncorr" >> "$W/build-records/binaries.sha256"
    cp "$W/build-$sha-$cfg/CMakeFiles/motioncorr_core.dir/flags.make" "$W/build-records/flags-$sha-$cfg.make"
    cp "$W/build-$sha-$cfg/CMakeCache.txt" "$W/build-records/cache-$sha-$cfg.txt"
  done
done
