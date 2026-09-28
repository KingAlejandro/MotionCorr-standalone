#!/usr/bin/env bash
# Revalidate the ported tooling against the RETAINED native two-GPU outputs.
#
# The C++ change is byte-identical to the one already witnessed natively at
# PR106 `f433662` (24/24 exact, two distinct physical UUIDs; see
# ../GPU_ACCEPTANCE.md), apart from one reworded comment. The tooling is what
# changed in this port, so the tooling is what is re-run -- over the outputs the
# native run already produced.
#
# NO GPU COMPUTE. Nothing here launches a CUDA worker or allocates a device.
# The aggregate step runs the stock binary CPU-side over an already-complete
# tree, so --only_do_unfinished processes zero movies; that is precisely the
# property the new no-rewrite guard asserts.
#
# Usage: revalidate_retained_native.sh <retained_run_dir> <ported_src> <out_dir>
set -euo pipefail
set -x

RUN="${1:?retained run dir, e.g. /home/alex/mc-i53-gpu/run}"
SRC="${2:?ported source tree}"
OUT="${3:?scratch output dir}"
# tools/compare_motioncorr.py needs numpy, which on this host lives only in
# ~/.mc-venv; /usr/bin/python3 has none.
PY="${MC_PYTHON:-$HOME/.mc-venv/bin/python3}"
MASK="96-111"
"$PY" -c 'import numpy; print("numpy", numpy.__version__)'

mkdir -p "$OUT"
cd "$RUN"

echo "=== PROVENANCE ==="
git -C "$SRC" rev-parse HEAD
git -C "$SRC" status --porcelain
date -Is; hostname; cat /proc/loadavg
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
echo '--- compute apps before (must be empty of ours) ---'
nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader || true

echo "=== RETAINED WITNESS (read, not reproduced) ==="
"$PY" -c "
import json
s = json.load(open('sh2/status.json'))
w = s['gpu_witness']
print('launcher_verdict', s['verdict'])
print('distinct_devices_witnessed', w['distinct_devices_witnessed'])
print('uuids', sorted(set(w['expected'].values())))
print('unwitnessed', w['unwitnessed_pids'], 'wrong', w['wrong_device'], 'shared', w['shared_devices'])
print('cpu_masks', s['cpu_masks'])
assert w['all_pids_witnessed_on_intended_distinct_devices']
assert len(set(w['expected'].values())) == 2
"

echo "=== 1. PARTITION DETERMINISM AT THE PORT HEAD ==="
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/partition_star.py" \
    --star movies.star --n 2 --outdir "$OUT/shards" --prefix shard
"$PY" - "$OUT" <<'PYEOF'
import hashlib, json, sys, pathlib
out = pathlib.Path(sys.argv[1])
old = json.loads(pathlib.Path("sh2/shards/shard_manifest.json").read_text())
new = json.loads((out / "shards" / "shard_manifest.json").read_text())
for k in ("canonical_movies", "canonical_output_roots", "n_movies", "n_shards"):
    assert old[k] == new[k], k
for a, b in zip(old["shards"], new["shards"]):
    assert a["movies"] == b["movies"], (a["index"], "assignment differs")
def d(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
for k in range(2):
    a = d(f"sh2/shards/shard_2way_{k}.star")
    b = d(out / "shards" / f"shard_2way_{k}.star")
    assert a == b, (k, a, b)
    print(f"shard {k} sha256 {a} IDENTICAL")
print("PARTITION_IDENTICAL=1")
PYEOF

echo "=== 2a. THE RETAINED STATUS IS REFUSED BY THE NEW BINDING ==="
set +e
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/merge_workers.py" \
    --manifest "$OUT/shards/shard_manifest.json" --workers sh2/w0 sh2/w1 \
    --status sh2/status.json --out "$OUT/merged_oldstatus"
OLDSTATUS_RC=$?
set -e
echo "OLDSTATUS_RC=$OLDSTATUS_RC  (2 expected: it predates manifest_sha256)"
[ "$OLDSTATUS_RC" -eq 2 ]

echo "=== 2b. MERGE WITH THE RETAINED RUN'S OWN FACTS, RE-RECORDED ==="
# Not a new claim about the run: every field below is copied out of the
# retained status. Only the path resolution and the manifest digest the new
# binding requires are added.
"$PY" - "$OUT" <<'PYEOF'
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[1])
old = json.loads(pathlib.Path("sh2/status.json").read_text())
man = (out / "shards" / "shard_manifest.json").resolve()
upgraded = dict(old)
upgraded["manifest"] = str(man)
upgraded["manifest_sha256"] = hashlib.sha256(man.read_bytes()).hexdigest()
upgraded["workers"] = [
    {**w, "log": str(pathlib.Path(f"sh2/w{w['index']}/run.log").resolve())}
    for w in old["workers"]]
(out / "status_upgraded.json").write_text(json.dumps(upgraded, indent=2) + "\n")
print("re-recorded exit codes:", [w["returncode"] for w in upgraded["workers"]])
print("re-recorded verdict:", upgraded["verdict"])
PYEOF
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/merge_workers.py" \
    --manifest "$OUT/shards/shard_manifest.json" --workers sh2/w0 sh2/w1 \
    --status "$OUT/status_upgraded.json" --out "$OUT/merged" \
    --report "$OUT/merge_report.json" \
    --aggregate-with /home/alex/mc-i53-gpu/build-final/motioncorr \
    --input-star movies.star \
    --aggregate-args='--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --j 4 --max_io_threads 4'
"$PY" -c "
import json
r = json.load(open('$OUT/merge_report.json'))
print('verdict', r['verdict'], 'staged', r['n_files_staged'], 'expected', r['n_movies_expected'])
print('problems', r['problems'])
assert r['verdict'] == 'PASS'
assert r['n_movies_expected'] == 24
assert r['aggregate_star']['row_order'] == 'canonical'
"

echo "=== 3. EXACT COMPARISON, 24 PAIRS, SERIAL CUDA vs TWO-WORKER TWO-GPU ==="
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/compare24.py" \
    --ref serialG --test "$OUT/merged" \
    --tool "$SRC/tools/compare_motioncorr.py" \
    --manifest "$OUT/shards/shard_manifest.json" --out "$OUT/exact"
"$PY" -c "
import json
s = json.load(open('$OUT/exact/exact_summary.json'))
print('expected', s['n_expected'], 'compared', s['n_compared'], 'passed', s['passed'], 'failed', s['failed'], s['verdict'])
assert s['verdict'] == 'PASS' and s['passed'] == 24 and s['failed'] == 0
ids = {r['report'] for r in s['results']}
assert len(ids) == 24, ids
"

echo "=== 4. REUSE ROUND TRIP, BOTH DIRECTIONS ==="
# Into a COPY of the comparison directory. Reusing $OUT/exact would leave its
# summary.json holding the tamper end state (23/1 FAIL), so the only retained
# artifact for step 3 would contradict the 24/24 it is evidence for.
cp -a "$OUT/exact" "$OUT/exact_reuse"
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/compare24.py" \
    --ref serialG --test "$OUT/merged" \
    --tool "$SRC/tools/compare_motioncorr.py" \
    --manifest "$OUT/shards/shard_manifest.json" --out "$OUT/exact_reuse" --reuse
SIDE=$(ls "$OUT/exact_reuse"/*.origin.json | head -1)
"$PY" -c "
import json,sys
p='$SIDE'; d=json.load(open(p)); d['tool_sha256']='0'*64
open(p,'w').write(json.dumps(d))
print('tampered', p)
"
set +e
taskset -c "$MASK" "$PY" "$SRC/tools/multi_gpu/compare24.py" \
    --ref serialG --test "$OUT/merged" \
    --tool "$SRC/tools/compare_motioncorr.py" \
    --manifest "$OUT/shards/shard_manifest.json" --out "$OUT/exact_reuse" --reuse
TAMPER_RC=$?
set -e
echo "TAMPER_RC=$TAMPER_RC  (1 expected)"
[ "$TAMPER_RC" -eq 1 ]

echo "=== RELEASE ==="
date -Is
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader || true
cat /proc/loadavg
echo "REVALIDATION COMPLETE"
