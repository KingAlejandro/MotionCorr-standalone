#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-hygiene239
mkdir -p "$W/unfixed/src" "$W/logs"
cd "$W/src"
for f in error.cpp error.h; do git show c8844894:src/$f > "$W/unfixed/src/$f"; done
for arm in before after; do
  inc=()
  source=src/error.cpp
  if [ "$arm" = before ]; then inc=(-I"$W/unfixed"); source="$W/unfixed/src/error.cpp"; fi
  taskset -c 112-119 g++ -std=c++17 -O3 -DNDEBUG -g -fno-omit-frame-pointer -fsanitize=address "${inc[@]}" -I. tests/test_relion_error_ownership.cpp "$source" -o "$W/error-$arm" > "$W/logs/sanitizer-build-$arm.log" 2>&1
  echo "sanitizer build $arm rc=0"
  for path in unprinted copies; do
    args=(); [ "$path" = unprinted ] && args=(--unprinted)
    set +e
    ASAN_OPTIONS=detect_leaks=1:exitcode=77 taskset -c 112-119 "$W/error-$arm" "${args[@]}" > "$W/logs/sanitizer-$arm-$path.log" 2>&1
    rc=$?
    set -e
    echo "$rc" > "$W/logs/sanitizer-$arm-$path.exit"
    echo "sanitizer $arm $path rc=$rc"
    if [ "$arm" = after ]; then [ "$rc" = 0 ]; else [ "$rc" != 0 ]; fi
  done
done
