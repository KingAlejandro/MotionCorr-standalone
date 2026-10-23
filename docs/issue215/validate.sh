#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-215
exec 8>"$W/validation.lock"
flock -n 8 || exit 73
exec >"$W/validation.log" 2>&1
trap 'echo DRIVER_EXIT=$? $(date -u +%FT%TZ)' EXIT
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID
cd "$W/src"
echo "HEAD=$(git rev-parse HEAD) CPUs=64-71 GPU=$CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=index,uuid,name --format=csv
# An earlier build may have survived a transport loss. Do not overlap it.
for i in $(seq 1 180); do
  if ! pgrep -f '^bash /mnt/clathrin/alex-motioncorr-215/build.sh$' >/dev/null; then break; fi
  sleep 5
done
if pgrep -f '^bash /mnt/clathrin/alex-motioncorr-215/build.sh$' >/dev/null; then exit 74; fi
bash "$W/build.sh"
echo ALL_BUILDS_RC=0
mkdir -p "$W/fixed" "$W/unfixed"
cp "$W/build-nvcomp/motioncorr" "$W/fixed/"
cp "$W/build-nvcomp/motioncorr_tiff_identity" "$W/fixed/"
gpu_run() {
  (
    exec 9>/tmp/motioncorr-gpu3-correctness.lock
    for i in $(seq 1 180); do
      if flock -n 9; then
        if ! nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$CUDA_VISIBLE_DEVICES" && flock -n /tmp/motioncorr-bench.lock true; then
          echo "GPU_RUN $(date -u +%FT%TZ) $*"
          taskset -c 64-71 "$@"
          exit $?
        fi
        flock -u 9
      fi
      sleep 10
    done
    exit 75
  )
}
gpu_run python3 tests/run_tiff_identity_controls.py --binary "$W/fixed/motioncorr_tiff_identity" --workdir "$W/control-fixed" > "$W/control-fixed.log" 2>&1
echo CONTROL_FIXED_RC=0
# Same test/shim, with only the production CUDA file reverse-applied.
git show c8844894:src/acc/cuda/cuda_movie_session.cu > src/acc/cuda/cuda_movie_session.cu
restore() { git restore src/acc/cuda/cuda_movie_session.cu; }
trap 'rc=$?; restore; echo DRIVER_EXIT=$rc $(date -u +%FT%TZ)' EXIT
taskset -c 64-71 cmake --build "$W/build-nvcomp" -j8 --target motioncorr motioncorr_tiff_identity > "$W/build-unfixed.log" 2>&1
echo UNFIXED_BUILD_RC=0
cp "$W/build-nvcomp/motioncorr" "$W/unfixed/"
cp "$W/build-nvcomp/motioncorr_tiff_identity" "$W/unfixed/"
restore
taskset -c 64-71 cmake --build "$W/build-nvcomp" -j8 > "$W/build-restored.log" 2>&1
echo RESTORED_BUILD_RC=0
set +e
gpu_run python3 tests/run_tiff_identity_controls.py --binary "$W/unfixed/motioncorr_tiff_identity" --workdir "$W/control-unfixed" > "$W/control-unfixed.log" 2>&1
rc=$?
set -e
echo CONTROL_UNFIXED_RC=$rc
[ "$rc" = 1 ]
python3 - <<'PY'
import json
from pathlib import Path
w=Path('/mnt/clathrin/alex-motioncorr-215')
rows=json.loads((w/'control-unfixed/result.json').read_text())
assert len(rows)==9 and all(r['passed'] for r in rows[:3])
assert all(r['swapped'] and not r['passed'] for r in rows[3:]), rows
print('negative control: six observed mutations, six rejected rows')
PY
for cfg in cpu cuda nvcomp; do
  if [ "$cfg" = cpu ]; then
    taskset -c 64-71 ctest --test-dir "$W/build-$cfg" --output-on-failure -j1 --output-junit "$W/ctest-$cfg.xml" > "$W/ctest-$cfg.log" 2>&1
  else
    gpu_run ctest --test-dir "$W/build-$cfg" --output-on-failure -j1 --output-junit "$W/ctest-$cfg.xml" > "$W/ctest-$cfg.log" 2>&1
  fi
  echo "CTEST_$cfg=0"
done
gpu_run python3 "$W/native_tutorial.py" --work "$W" > "$W/native-tutorial.log" 2>&1
echo NATIVE_TUTORIAL_RC=0
sha256sum "$W"/build-{cpu,cuda,nvcomp}/motioncorr "$W"/{fixed,unfixed}/motioncorr* > "$W/binaries.sha256"
echo VALIDATION_COMPLETE
