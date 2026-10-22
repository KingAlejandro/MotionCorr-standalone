#!/usr/bin/env bash
set -Eeuo pipefail
W=/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z
cd "$W"
trap 'rc=$?; date -u +%FT%TZ > logs/complete-build.finished; printf "%s\n" "$rc" > logs/complete-build.exit; exit "$rc"' EXIT
printf '%s\n' "$$" > logs/complete-build.pid
date -u +%FT%TZ > logs/complete-build.started
export PATH=/usr/local/cuda-12.8/bin:/home/alex/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec 8>/tmp/motioncorr-build.lock
flock -n 8
# Reconcile the first driver, which compiled only selected executables. CTest's
# full-collection validator also needs the unrelated registered programs to exist.
test -f logs/build.exit
test "$(cat logs/compile.exit)" = 0
test "$(cat logs/host-controls.exit)" = 0
test "$(cat logs/collection-control.exit)" = 0
run() {
    local name=$1; shift
    printf '%q ' "$@" >> logs/commands.txt; printf '\n' >> logs/commands.txt
    set +e
    "$@" > "logs/$name.log" 2>&1
    local rc=$?
    set -e
    printf '%s\n' "$rc" > "logs/$name.exit"
    return "$rc"
}
run compile-remaining cmake --build build --parallel 2
run collection-final ctest --test-dir build --show-only=json-v1
run collection-validation-final /home/alex/.mc-venv/bin/python3 src/tools/validate_test_collection.py --json logs/collection-final.log --cuda --dump-json logs/collection-validation-final.json
cp logs/collection-final.log logs/collection-for-missing.log
run missing-controls /home/alex/.mc-venv/bin/python3 support/missing_controls.py
(cd src && sha256sum -c ../support/production-source.sha256) > logs/production-source-verified.log
find src/src src/tests src/tools -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > logs/actual-build-inputs.sha256
find build -type f \( -name '*.make' -o -name 'link.txt' -o -name '*.cmake' -o -name 'CMakeCache.txt' -o -name 'Makefile' \) -print0 | sort -z | xargs -0 sha256sum > logs/generated-build-files.sha256
sha256sum build/motioncorr build/cuda_local_admission build/motioncorr_faultinject build/motioncorr_streaming_plan_fault build/patch_retry_admission build/patch_retry_state > logs/binaries.sha256
cp build/CMakeCache.txt logs/
for target in motioncorr_core motioncorr cuda_local_admission motioncorr_faultinject motioncorr_streaming_plan_fault; do
    cp "build/CMakeFiles/$target.dir/flags.make" "logs/$target-flags.make"
    cp "build/CMakeFiles/$target.dir/link.txt" "logs/$target-link.txt"
done
