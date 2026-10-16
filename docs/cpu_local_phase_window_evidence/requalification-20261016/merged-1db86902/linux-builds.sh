#!/bin/bash
set -u
cd /home/ubuntu/fix183-20261016
export PATH="$HOME/.mc-venv/bin:$PATH" OMP_NUM_THREADS=6 OMP_THREAD_LIMIT=6
# Run this driver under taskset -c 56-61; children inherit the exclusive lane.
step() {
  name=$1; shift
  printf '%s\n' "$*" > "logs/$name.command"
  bash -c "$*" > "logs/$name.log" 2>&1
  rc=$?; echo "$rc" > "logs/$name.status"
  return "$rc"
}
step release-build 'cd /home/ubuntu/fix183-20261016/candidate && ~/.mc-venv/bin/cmake -S . -B build-release -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3 && ~/.mc-venv/bin/cmake --build build-release -j4' || exit 1
step release-ctest 'cd /home/ubuntu/fix183-20261016/candidate && ~/.mc-venv/bin/ctest --test-dir build-release --output-on-failure' || exit 2
step debug-build 'cd /home/ubuntu/fix183-20261016/candidate && ~/.mc-venv/bin/cmake -S . -B build-debug -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS_DEBUG="-O0 -g" -DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3 && ~/.mc-venv/bin/cmake --build build-debug -j4' || exit 3
step debug-ctest 'cd /home/ubuntu/fix183-20261016/candidate && ~/.mc-venv/bin/ctest --test-dir build-debug --output-on-failure' || exit 4
step base-build 'cd /home/ubuntu/fix183-20261016/base-178 && ~/.mc-venv/bin/cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3 && ~/.mc-venv/bin/cmake --build build -j4' || exit 5
step witnesses 'cd /home/ubuntu/fix183-20261016 && candidate/build-release/cpu_patch_phase_window && candidate/build-debug/cpu_patch_phase_window && sha256sum candidate/build-{release,debug}/{motioncorr,cpu_patch_phase_window} base-178/build/motioncorr && uname -a && lscpu && free -h && ps -eo user,pid,pcpu,comm --sort=-pcpu | head -15' || exit 6
echo complete > logs/builds.done
