#!/bin/bash
set -euo pipefail
D=/home/ubuntu/mc-io-merge-evidence
BASE=/home/ubuntu/mc-io-evidence
source /home/ubuntu/.mc-venv/bin/activate
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$D"
for label in standalone combined;do
 python3 harness/release_reader.py --source "$D/src-$label" --build "$D/src-$label/build-cpu" --output "$D/dump-release-$label" --json "$D/evidence/release-reader-build-$label.json" > "evidence/release-reader-build-$label.log" 2>&1
 sha256sum "dump-release-$label" >> evidence/release-reader-binaries.sha256
 python3 harness/strip_rejection.py --repo "$D/src-$label" --dumper "$D/dump-release-$label" --shim "$D/strip_fault_inject.so" --work "$D/release-strips-$label" --json "$D/evidence/release-strip-rejections-$label.json" > "evidence/release-strip-rejections-$label.log" 2>&1
 python3 harness/compare_decoded.py --repo "$D/src-$label" --ref-dumper "$BASE/dump_decoded_main" --test-dumper "$D/dump-release-$label" --work "$D/release-decoded-$label" --json "$D/evidence/release-decoded-$label.json" > "evidence/release-decoded-$label.log" 2>&1
done
printf 'COMPLETE\n' > evidence/RELEASE_COMPONENT_COMPLETE
