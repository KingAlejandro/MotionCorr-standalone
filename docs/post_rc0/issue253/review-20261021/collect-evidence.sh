#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-254-review-20261021
for attempt in $(seq 1 360); do
 test ! -f "$S/logs/ctest-cpu.exit" || break
 sleep 5
done
test -f "$S/logs/ctest-cpu.exit"
mkdir -p "$S/retained"
for type in cpu cuda nvcomp; do
 cp "$S/build-$type/CMakeCache.txt" "$S/retained/CMakeCache-$type.txt"
 taskset -c 80-87 ctest --test-dir "$S/build-$type" --show-only=json-v1 > "$S/retained/tests-$type.json"
 cp "$S/build-$type/Testing/Temporary/LastTest.log" "$S/retained/LastTest-$type.log"
done
for name in cuda_movie_session_no_projection cuda_fft_prep_wrapper_no_projection cuda_realspace_dw_dose_no_projection cuda_alignpatch_ccf_perpatch_no_projection cuda_alignpatch_ccf_batched_no_projection; do
 cp "$S/build-nvcomp/mutants/$name.cu" "$S/retained/"
done
cp /mnt/clathrin/mc254-run.sh /mnt/clathrin/mc254-resume-gpu3.sh /mnt/clathrin/mc254-extra-gpu3.sh /mnt/clathrin/mc254-inject.sh /mnt/clathrin/mc254-rerun-ci.sh "$S/retained/"
cp "$S/boundary_injection.cu" "$S/retained/"
{ date -u; git -C "$S/src" rev-parse HEAD; git -C "$S/src" status --porcelain; sha256sum "$S/src/CMakeLists.txt" "$S/src/tests/cuda_hermitian_inverse.cpp" "$S/src/tests/cuda_hermitian_check.h" "$S/src/tests/cuda_patch_batch.cpp" "$S/boundary_injection.cu"; } > "$S/logs/final-source-identity.log"
taskset -c 80-87 tar -czf "$S/review-raw.tar.gz" -C "$S" logs retained
sha256sum "$S/review-raw.tar.gz" > "$S/review-raw.sha256"
echo done > "$S/collection.done"
