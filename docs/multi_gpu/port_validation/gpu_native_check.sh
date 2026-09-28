#!/usr/bin/env bash
# The two things the CPU evidence and the retained-output revalidation cannot cover.
#
# 1. A CUDA BUILD. The ported --gpu hunk splits on `#if defined _CUDA_ENABLED`, and
#    every CPU build compiles the other side. The live path -- textToInteger,
#    accGPUGetDeviceCount, use_gpu = true -- has never been through a compiler on
#    this branch. This needs nvcc, not a device.
#
# 2. ONE SMALL NATIVE RUN. No real launcher run has ever produced a status.json in
#    the new format (resolved paths + manifest_sha256), so the merge's accept path
#    on real GPU output has only been exercised against a status re-recorded by
#    hand. Four movies across two workers on two devices closes that, and
#    exercises real nvidia-smi witnessing and the new per-worker timing/RSS fields
#    at the same time.
#
# Deliberately NOT re-run: the 24/24 exact equality. The C++ is byte-identical to
# the natively witnessed version apart from one reworded comment.
#
# Devices are selected BY UUID. nvidia-smi ignores CUDA_VISIBLE_DEVICES, so an
# ordinal is never treated as device identity.
#
# Usage: gpu_native_check.sh <src> <out> <uuid_a> <uuid_b>
set -euo pipefail
set -x

SRC="${1:?ported source tree}"
OUT="${2:?scratch dir}"
UUID_A="${3:?first device UUID}"
UUID_B="${4:?second device UUID}"
PY="${MC_PYTHON:-$HOME/.mc-venv/bin/python3}"
CUDA=/usr/local/cuda-12.8
BUILD="$OUT/build-cuda"
MASK="96-111"
BUILD_MASK="96-103"
export PATH="$CUDA/bin:$PATH"

mkdir -p "$OUT"

echo "=== PROVENANCE ==="
git -C "$SRC" rev-parse HEAD
git -C "$SRC" status --porcelain
[ -z "$(git -C "$SRC" status --porcelain)" ]
date -Is; hostname; nvcc --version | tail -2
nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1
"$PY" -c 'import numpy; print("numpy", numpy.__version__)'

echo "=== OCCUPANCY BEFORE (owned devices only) ==="
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader || true
for u in "$UUID_A" "$UUID_B"; do
    used=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$u" || true)
    echo "owned device $u has $used compute app(s)"
    [ "$used" -eq 0 ]
done

echo "=== 1. CUDA BUILD (nvcc; no device is opened) ==="
rm -rf "$BUILD"
taskset -c "$BUILD_MASK" cmake -S "$SRC" -B "$BUILD" \
    -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DBUILD_TESTING=OFF \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DPython3_EXECUTABLE="$PY"
set +e
taskset -c "$BUILD_MASK" cmake --build "$BUILD" -j 8 2>&1 | tee "$OUT/cuda_build.log"
BUILD_RC=${PIPESTATUS[0]}
set -e
echo "CUDA_BUILD_RC=$BUILD_RC"
[ "$BUILD_RC" -eq 0 ]
grep -c "error:" "$OUT/cuda_build.log" || true
sha256sum "$BUILD/motioncorr"
# the branch that a CPU build never compiles must be in this binary
strings "$BUILD/motioncorr" | grep -c "Using CUDA acceleration on GPU device"

echo "=== 1b. DEVICE-LIST BEHAVIOUR ON A CUDA BUILD ==="
for spec in "0:1:2:3" "0,1" "0abc" "-1" "99"; do
    echo "--- --gpu $spec ---"
    set +e
    CUDA_VISIBLE_DEVICES="$UUID_A" "$BUILD/motioncorr" --use_own \
        --i /nonexistent.star --o "$OUT/none" --gpu "$spec" 2>&1 | tail -3
    echo "rc=${PIPESTATUS[0]}"
    set -e
done

echo "=== 2. SMALL NATIVE RUN: 4 MOVIES, 2 WORKERS, 2 DEVICES ==="
cd "$OUT"
"$PY" - "$SRC" <<'PYEOF'
import pathlib, sys, shutil
src = pathlib.Path(sys.argv[1])
run = pathlib.Path("/home/alex/mc-i53-gpu/run")
full = (run / "movies.star").read_text().splitlines(keepends=True)
head, rows = [], []
seen_loop = False
for line in full:
    if line.startswith("_rlnMicrograph") or not seen_loop:
        head.append(line)
        if line.strip().startswith("_rlnMicrographPreExposure"):
            seen_loop = True
        continue
    if line.strip():
        rows.append(line)
pathlib.Path("movies4.star").write_text("".join(head) + "".join(rows[:4]) + "\n")
print("rows kept:", [r.split()[0] for r in rows[:4]])
PYEOF
ln -sfn /home/alex/mc-i53-gpu/run/Movies Movies

taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/run_multi_gpu.py" \
    --star movies4.star --out native --binary "$BUILD/motioncorr" \
    --devices "$UUID_A,$UUID_B" --cpus "96-103;104-111" --sample-interval 0.25 \
    -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
       --bfactor 150 --gainref Movies/gain.mrc --j 4 --max_io_threads 4

"$PY" -c "
import json
s = json.load(open('native/status.json'))
w = s['gpu_witness']
print('verdict', s['verdict'])
print('distinct UUIDs', sorted(set(w['expected'].values())))
print('unwitnessed', w['unwitnessed_pids'], 'wrong', w['wrong_device'], 'shared', w['shared_devices'])
print('samples', w['n_samples'], 'sampler_errors', w['sampler_errors'])
print('tail_s', s['final_worker_tail_seconds'])
for x in s['workers']:
    print(' worker', x['index'], 'rc', x['returncode'], 'wall', x['wall_seconds'],
          'rss_hwm_kib', x['rss_hwm_kib'], 'mask', s['cpu_masks'][x['index']])
assert s['verdict'] == 'PASS'
assert w['all_pids_witnessed_on_intended_distinct_devices']
assert len(set(w['expected'].values())) == 2
assert s['manifest_sha256'] and s['final_worker_tail_seconds'] is not None
assert all(x['rss_hwm_kib'] and x['rss_hwm_kib'] > 0 for x in s['workers'])
"

echo "=== 3. MERGE ACCEPTS THE REAL NEW-FORMAT STATUS ==="
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/merge_workers.py" \
    --manifest native/shards/shard_manifest.json \
    --workers native/w0 native/w1 --status native/status.json \
    --out merged --report merge_report.json \
    --aggregate-with "$BUILD/motioncorr" --input-star movies4.star \
    --aggregate-args='--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --j 4 --max_io_threads 4'
"$PY" -c "
import json
r = json.load(open('merge_report.json'))
print('verdict', r['verdict'], 'staged', r['n_files_staged'], 'expected', r['n_movies_expected'])
print('problems', r['problems'])
assert r['verdict'] == 'PASS' and r['n_movies_expected'] == 4
assert r['aggregate_star']['row_order'] == 'canonical'
"

echo "=== 4. THE FOUR MOVIES MATCH THE RETAINED SERIAL CUDA BASELINE ==="
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/compare24.py" \
    --ref /home/alex/mc-i53-gpu/run/serialG --test merged \
    --tool "$SRC/tools/compare_motioncorr.py" \
    --manifest native/shards/shard_manifest.json --out exact
"$PY" -c "
import json
s = json.load(open('exact/exact_summary.json'))
print('expected', s['n_expected'], 'passed', s['passed'], 'failed', s['failed'], s['verdict'])
assert s['verdict'] == 'PASS' and s['passed'] == 4 and s['failed'] == 0
"

echo "=== RELEASE ==="
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null || true)
    case "$exe" in *"$OUT"*) echo "STRAY $pid $exe";; esac
done
date -Is
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader || true
echo "NATIVE CHECK COMPLETE"
