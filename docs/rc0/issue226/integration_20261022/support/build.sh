#!/usr/bin/env bash
set -Eeuo pipefail
W=/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z
cd "$W"
trap 'rc=$?; date -u +%FT%TZ > logs/build.finished; printf "%s\n" "$rc" > logs/build.exit; exit "$rc"' EXIT
printf '%s\n' "$$" > logs/build.pid
date -u +%FT%TZ > logs/build.started
export PATH=/usr/local/cuda-12.8/bin:/home/alex/.mc-venv/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec 8>/tmp/motioncorr-build.lock
flock -n 8
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
{ hostname; date -u; taskset -pc $$; free -b; df -B1 .; gcc --version; nvcc --version; cmake --version; /home/alex/.mc-venv/bin/python3 -c 'import sys,numpy;print(sys.version,numpy.__version__)'; ps -eo pid,psr,comm,args; } > logs/preparation.txt
sha256sum -c source.sha256 > logs/archive-verification.log
(cd src && sha256sum -c ../support/build-inputs.sha256) > logs/build-inputs-before.log
# Test-only D2 receipt overlay; production remains exactly the normal merge.
run receipt-overlay patch -d src -p1 -i ../support/native-receipts.patch
run configure cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
run compile cmake --build build --target motioncorr cuda_local_admission motioncorr_faultinject motioncorr_streaming_plan_fault patch_retry_admission patch_retry_state --parallel 2
run host-controls ctest --test-dir build -R '^(PatchRetryAdmission|PatchRetryState)$' --output-on-failure --parallel 1
run collection-control /home/alex/.mc-venv/bin/python3 src/tools/test_ci_fail_closed.py TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails
run collection ctest --test-dir build --show-only=json-v1
run collection-validation /home/alex/.mc-venv/bin/python3 src/tools/validate_test_collection.py --json logs/collection.log --cuda --dump-json logs/collection-validation.json
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
