#!/bin/bash
# Untimed native correctness for the composed candidate: serial vs 2- and
# 4-worker all-24 runs, plus the two failure/resume controls.
#
# Untimed on purpose. Wall times printed by the launcher are bookkeeping; the
# matched measurement is a separate job under an exclusive allocation.
#
# Usage: run_correctness_all24.sh <src> <build> <tutorial-root> <outdir> <uuid0,uuid1,uuid2,uuid3>
set -uo pipefail
SRC=$1; BUILD=$2; TUT=$3; OUT=$4; UUIDS=$5
PY=${PY:-python3}
MG=$SRC/tools/multi_gpu
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
      --bfactor 150 --gainref Movies/gain.mrc --j 4 --max_io_threads 4)
mkdir -p "$OUT"; cd "$TUT" || exit 9
exec > >(tee "$OUT/driver.log") 2>&1
IFS=',' read -r U0 U1 U2 U3 <<< "$UUIDS"

note() { echo; echo "##### $* #####"; }
rec()  { echo "$1=$2" >> "$OUT/results.txt"; }

note "provenance"
git -C "$SRC" rev-parse HEAD | tee "$OUT/source.txt"
git -C "$SRC" status --porcelain | tee "$OUT/source-status.txt"
sha256sum "$BUILD/motioncorr" | tee "$OUT/binary.sha256"
{ hostname; nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv;
  nvidia-smi topo -m; lscpu | head -25; nproc; } > "$OUT/topology.txt" 2>&1
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader \
  > "$OUT/occupancy-before.csv"
[ -s "$OUT/occupancy-before.csv" ] && { echo "REFUSING: devices not idle"; cat "$OUT/occupancy-before.csv"; exit 31; }
sha256sum movies.star Movies/gain.mrc > "$OUT/input.sha256"

# ---------------------------------------------------------------- A1 serial
note "A1 serial baseline, 1 worker, 24 movies"
$PY "$MG/run_multi_gpu.py" --star movies.star --out "$OUT/a1-serial" \
    --binary "$BUILD/motioncorr" --devices "$U0" --cpus 0-23 \
    --sample-interval 0.5 -- "${OPTS[@]}"
rec a1_serial_rc $?

# ---------------------------------------------------------------- A2/A4 sharded
for N in 2 4; do
  case $N in
    2) DEV="$U0,$U1";        MASK='0-11;12-23' ;;
    4) DEV="$U0,$U1,$U2,$U3"; MASK='0-5;6-11;12-17;18-23' ;;
  esac
  note "A$N sharded run, $N workers, devices $DEV, masks $MASK"
  $PY "$MG/run_multi_gpu.py" --star movies.star --out "$OUT/a$N-sharded" \
      --binary "$BUILD/motioncorr" --devices "$DEV" --cpus "$MASK" \
      --sample-interval 0.5 -- "${OPTS[@]}"
  rec "a${N}_launch_rc" $?
  # Shards must be disjoint and cover the input exactly.
  $PY - "$OUT/a$N-sharded/shards/shard_manifest.json" "$N" <<'PY' | tee -a "$OUT/results.txt"
import json,sys
m=json.load(open(sys.argv[1])); n=int(sys.argv[2])
shards=m["shards"]; sets=[set(s["movies"]) for s in shards]
allm=[x for s in shards for x in s["movies"]]
ok = len(shards)==n and len(allm)==len(set(allm)) and \
     all(not (a&b) for i,a in enumerate(sets) for b in sets[i+1:])
print(f"shards{n}_count={len(shards)}")
print(f"shards{n}_movies={len(allm)} unique={len(set(allm))}")
print(f"shards{n}_disjoint_and_complete={'PASS' if ok else 'FAIL'}")
PY
  note "A$N merge"
  $PY "$MG/merge_workers.py" --manifest "$OUT/a$N-sharded/shards/shard_manifest.json" \
      --workers "$OUT/a$N-sharded"/w[0-9]* --status "$OUT/a$N-sharded/status.json" \
      --out "$OUT/a$N-merged" --report "$OUT/a$N-merge-report.json" \
      --aggregate-with "$BUILD/motioncorr" --input-star movies.star \
      --aggregate-args "$(printf '%s ' "${OPTS[@]}")"
  rec "a${N}_merge_rc" $?
  note "C$N per-movie exact comparison vs serial"
  $PY "$MG/compare24.py" --ref "$OUT/a1-serial/w0" --test "$OUT/a$N-merged" \
      --tool "$SRC/tools/compare_motioncorr.py" \
      --manifest "$OUT/a$N-sharded/shards/shard_manifest.json" \
      --out "$OUT/c$N-compare.json"
  rec "c${N}_pixel_exact_rc" $?
  note "S$N structural grading vs serial (headers, extended headers, finite pixels, STAR inventory)"
  $PY - "$OUT/a$N-sharded/shards/shard_manifest.json" "$OUT/s$N-manifest.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
movies=[x for s in m["shards"] for x in s["movies"]]
json.dump({"movies":sorted(movies)}, open(sys.argv[2],"w"), indent=1)
PY
  $PY "$SRC/docs/issue85_laneC/compare_output_trees.py" \
      "$OUT/a1-serial/w0" "$OUT/a$N-merged" \
      --manifest "$OUT/s$N-manifest.json" --input-star movies.star \
      --json-out "$OUT/s$N-structural.json"
  rec "s${N}_structural_rc" $?
  note "C3-$N aggregate STAR identity"
  if diff -q <(grep -v '^# *version\|^ *$' "$OUT/a1-serial/w0/corrected_micrographs.star") \
             <(grep -v '^# *version\|^ *$' "$OUT/a$N-merged/corrected_micrographs.star") >/dev/null; then
     rec "c3_${N}_aggregate_star" IDENTICAL
  else
     rec "c3_${N}_aggregate_star" DIFFERS
     diff <(cat "$OUT/a1-serial/w0/corrected_micrographs.star") \
          <(cat "$OUT/a$N-merged/corrected_micrographs.star") > "$OUT/c3-$N-star.diff"
  fi
  note "witness A$N: UUID, actual pid, achieved mask"
  $PY - "$OUT/a$N-sharded/status.json" <<'PY' | tee -a "$OUT/results.txt"
import json,sys
s=json.load(open(sys.argv[1])); n=s["n_workers"]
w=s["workers"]; d=s.get("devices") or []
print(f"witness{n}_devices={d}")
print(f"witness{n}_pids={[x['pid'] for x in w]}")
print(f"witness{n}_masks={s.get('cpu_masks')}")
print(f"witness{n}_verdict={s.get('witness',{}).get('verdict') if isinstance(s.get('witness'),dict) else s.get('witness')}")
print(f"witness{n}_tail_s={s.get('final_worker_tail_seconds')}")
PY
done

# ---------------------------------------------------- A5 owned-child failure
note "A5 controlled owned-child failure: SIGKILL worker 0 of a 4-worker run"
( $PY "$MG/run_multi_gpu.py" --star movies.star --out "$OUT/a5-killed" \
      --binary "$BUILD/motioncorr" --devices "$U0,$U1,$U2,$U3" \
      --cpus '0-5;6-11;12-17;18-23' --sample-interval 0.5 -- "${OPTS[@]}" \
      > "$OUT/a5-launch.log" 2>&1 ; echo "a5_launch_rc=$?" >> "$OUT/results.txt" ) &
LPID=$!
# status.json is only written after the launcher exits, so it cannot identify a
# live worker. Match the real child on the shard path the launcher gave it.
W0=""
for _ in $(seq 1 180); do
  W0=$(pgrep -f -- "--i .*a5-killed/shards/shard_4way_0.star" | head -1)
  [ -n "$W0" ] && break
  sleep 1
done
echo "a5_target_pid=${W0:-NONE}" >> "$OUT/results.txt"
if [ -z "$W0" ]; then
  # No kill means no fault, and the FAIL verdict below would mean nothing.
  rec a5_control VACUOUS_NO_WORKER_FOUND
else
  kill -9 "$W0" && rec a5_control KILL_DELIVERED
fi
wait $LPID
sleep 3
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader \
  > "$OUT/a5-occupancy-after.csv"
rec a5_strays_on_owned_devices "$(grep -c -E "$U0|$U1|$U2|$U3" "$OUT/a5-occupancy-after.csv")"
note "A5 merge must refuse"
$PY "$MG/merge_workers.py" --manifest "$OUT/a5-killed/shards/shard_manifest.json" \
    --workers "$OUT/a5-killed"/w[0-9]* --status "$OUT/a5-killed/status.json" \
    --out "$OUT/a5-merged" --report "$OUT/a5-merge-report.json" \
    > "$OUT/a5-merge.log" 2>&1
rec a5_merge_rc $?   # must be non-zero
$PY - "$OUT/a5-killed/status.json" <<'PY' | tee -a "$OUT/results.txt"
import json,sys
try:
    st=json.load(open(sys.argv[1]))
except Exception as e:
    print(f"a5_status_readable=NO ({e})"); raise SystemExit
rcs=[w.get("returncode") for w in st.get("workers",[])]
print(f"a5_worker_returncodes={rcs}")
print(f"a5_worker0_signal_killed={'PASS' if rcs and rcs[0]==-9 else 'FAIL'}")
print(f"a5_other_workers_zero={'PASS' if all(r==0 for r in rcs[1:]) else 'FAIL'}")
PY

# ------------------------------------------------------- A6 non-prefix resume
note "A6 non-prefix resume: remove a non-prefix set of completed movies, resume"
cp -a "$OUT/a2-sharded" "$OUT/a6-resume"
$PY - "$OUT/a6-resume" <<'PY' | tee -a "$OUT/results.txt"
import json,sys,shutil
from pathlib import Path
root=Path(sys.argv[1])
man=json.load(open(root/"shards/shard_manifest.json"))
canon=[m for s in man["shards"] for m in s["movies"]]
canon=sorted(canon)
# Canonical indices 5-11 removed: not a prefix, so --only_do_unfinished cannot
# be satisfied by "continue from the end".
drop=set(canon[5:12])
removed=0
for w in sorted(root.glob("w[0-9]*")):
    for p in w.rglob("*"):
        if p.is_file() and any(Path(m).stem in p.name for m in drop):
            p.unlink(); removed+=1
print(f"a6_products_removed={removed}")
print(f"a6_dropped_indices=5-11 is_prefix=0")
print("a6_control=" + ("REMOVALS_MADE" if removed else "VACUOUS_NOTHING_REMOVED"))
PY
for IDX in 0 1; do
  W="$OUT/a6-resume/w$IDX"
  case $IDX in 0) D=$U0; M=0-11;; 1) D=$U1; M=12-23;; esac
  ( cd "$TUT" && CUDA_VISIBLE_DEVICES="$D" taskset -c "$M" \
      "$BUILD/motioncorr" --i "$OUT/a6-resume/shards/shard_2way_$IDX.star" \
      --o "$W/" --only_do_unfinished --gpu 0 "${OPTS[@]}" > "$W/resume.log" 2>&1 )
  rec "a6_worker${IDX}_resume_rc" $?
done
$PY "$MG/merge_workers.py" --manifest "$OUT/a6-resume/shards/shard_manifest.json" \
    --workers "$OUT/a6-resume"/w[0-9]* --status "$OUT/a6-resume/status.json" \
    --out "$OUT/a6-merged" --report "$OUT/a6-merge-report.json" \
    --aggregate-with "$BUILD/motioncorr" --input-star movies.star \
    --aggregate-args "$(printf '%s ' "${OPTS[@]}")"
rec a6_merge_rc $?
$PY "$MG/compare24.py" --ref "$OUT/a1-serial/w0" --test "$OUT/a6-merged" \
    --tool "$SRC/tools/compare_motioncorr.py" \
    --manifest "$OUT/a6-resume/shards/shard_manifest.json" --out "$OUT/a6-compare.json"
rec a6_pixel_exact_rc $?

nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader \
  > "$OUT/occupancy-after.csv"
date -u > "$OUT/finished.txt"
note "SUMMARY"; cat "$OUT/results.txt"
