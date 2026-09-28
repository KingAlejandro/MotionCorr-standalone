#!/usr/bin/env bash
set -euo pipefail
exec 200>/tmp/motioncorr-issue96-cpu-validation.lock
flock -w 1200 200
cd "$HOME"
if [ ! -d mc-pr103-fix-433f04e ]; then git clone mc-pr103-fix-source.bundle mc-pr103-fix-433f04e; fi
cd mc-pr103-fix-433f04e
mkdir -p evidence
exec > >(tee evidence/validation.log) 2>&1
date -Is
hostname
uname -a
git rev-parse HEAD
git status --short
sha256sum ../mc-pr103-fix-source.bundle test-data/synthetic/synthetic_movie.tiff
numactl --hardware
numactl --show
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/self/status
ps -eo pid,pcpu,psr,comm,args --sort=-pcpu | head -15 || true
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE
source "$HOME/.mc-venv/bin/activate"
cmake --version
g++ --version | head -1
pkg-config --modversion libtiff-4
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON
cmake --build build -j 16
sha256sum build/motioncorr build/runner_numerics
ctest --test-dir build --output-on-failure
python3 tests/test_damaged_movie.py --binary build/motioncorr
printf 'RESULT=PASS\n'
date -Is
