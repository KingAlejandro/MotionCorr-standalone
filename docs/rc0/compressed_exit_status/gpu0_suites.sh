#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-214
export PATH=$W/tools/usr/bin:/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
cd "$W/src"
flock -n /tmp/motioncorr-bench.lock true
exec 9>/tmp/motioncorr-gpu0-correctness.lock
flock 9
if nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$CUDA_VISIBLE_DEVICES"; then exit 80; fi
for cfg in cuda nvcomp; do
 B=$W/build-$cfg
 O=$W/ctest-$cfg
 {
 echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l)"
 echo "mask 88-95 gpu $CUDA_VISIBLE_DEVICES lock /tmp/motioncorr-gpu0-correctness.lock"
 sha256sum "$B/motioncorr"
 taskset -c 88-95 python3 tools/validate_test_collection.py --test-dir "$B"
 set +e
 taskset -c 88-95 ctest --test-dir "$B" --output-on-failure -j1 --output-junit "$O.junit.xml"
 rc=$?
 set -e
 echo "$rc" > "$O.exit"
 echo "ctest rc=$rc end $(date -u +%FT%TZ)"
 [ "$rc" = 0 ] || exit "$rc"
 } > "$O.log" 2>&1
 echo "$cfg PASS"
 done
sha256sum "$W"/build-{cpu,cuda,nvcomp}/motioncorr > "$W/logs/binaries.sha256"
echo SUITES_DONE
