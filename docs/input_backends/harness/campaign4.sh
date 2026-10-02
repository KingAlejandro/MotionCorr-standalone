#!/bin/bash
# Input-backends campaign v4.
#
# Both arms are built from scratch inside this lock acquisition with one script
# and one set of flags, so build provenance is not a variable: campaign 2's
# baseline was configured hours earlier and its candidate was an incremental
# rebuild, and its null control (identical code, identical route) came out
# 0.5-1.0 s apart under a load that rose from 2.3 to 14 during the series.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
TIMED="u16_deflate_rps1 u8_lzw_rps1 u8_deflate_rps1 u16_deflate_rps8"
EDGE="u16_lzw_rps1 u16_deflate_rps2 u16_deflate_rps512 u8_deflate_rps16 u8_lzw_rps64 u16_deflate_pred2 u16_raw_rps1"
F48="u16_deflate_rps1_48f u8_lzw_rps1_48f u8_deflate_rps1_48f"
REPEATS=${REPEATS:-9}
say() { echo "[$(date -u +%FT%TZ)] $*"; }

say "BUILD both arms from scratch, same script and flags"
taskset -c $MASK $W/tools/build.sh $W/src-base $W/bld-baseb || { say "FATAL build base"; exit 1; }
taskset -c $MASK $W/tools/build.sh $W/src-u8b  $W/bld-u8c  || { say "FATAL build cand"; exit 1; }

t0=$(date +%s)
while [ $(( $(pgrep -x cc1plus|wc -l)+$(pgrep -x nvcc|wc -l)+$(pgrep -x cicc|wc -l)+$(pgrep -x ptxas|wc -l) )) -gt 0 ]; do
  [ $(( $(date +%s) - t0 )) -ge 180 ] && break; sleep 5
done
say "SETTLE waited=$(( $(date +%s) - t0 ))s compilers=$(( $(pgrep -x cc1plus|wc -l)+$(pgrep -x nvcc|wc -l)+$(pgrep -x cicc|wc -l)+$(pgrep -x ptxas|wc -l) )) load1=$(cut -d' ' -f1 /proc/loadavg)"

GPU=""; GPU_UUID=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")" -eq 0 ] && { GPU=$idx; GPU_UUID=$uuid; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no free GPU"; exit 1; }
say "TARGET gpu_index=$GPU uuid=$GPU_UUID"
BASE=$W/bld-baseb/motioncorr; CAND=$W/bld-u8c/motioncorr
say "BINARIES base=$(sha256sum $BASE|cut -c1-16) cand=$(sha256sum $CAND|cut -c1-16)"

say "CTEST on both builds"
(cd $W/bld-baseb && taskset -c $MASK ctest -j1 > $W/logs/ctest-baseb.log 2>&1; echo "CTEST base rc=$?")
(cd $W/bld-u8c   && taskset -c $MASK ctest --output-on-failure -j1 > $W/logs/ctest-u8c.log 2>&1; echo "CTEST cand rc=$?")
grep -hE "tests passed|tests failed" $W/logs/ctest-baseb.log $W/logs/ctest-u8c.log | sed 's/^/    /'

run_one() {
  local arm=$1 var=$2 out=$3 bin
  [ "$arm" = base ] && bin=$BASE || bin=$CAND
  local l0 fa0 t_start t_end
  l0=$(cut -d' ' -f1 /proc/loadavg)
  fa0=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$GPU_UUID")
  t_start=$(date +%s.%N)
  taskset -c $MASK $W/tools/run_matrix.sh "$bin" "$W/inputs/$var" "$out" "$GPU" > "$out.summary" 2>&1
  t_end=$(date +%s.%N)
  printf 'RESULT arm=%s variant=%s rc=%s elapsed=%.3f rss_kb=%s user_s=%s sys_s=%s products=%s load_pre=%s load_post=%s gpuapps=%s/%s routes=[%s]\n' \
    "$arm" "$var" "$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1)" "$(echo "$t_end - $t_start"|bc)" \
    "$(grep -oP '(?<=Maximum resident set size \(kbytes\): )\d+' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=User time \(seconds\): ).*' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=System time \(seconds\): ).*' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=^PRODUCTS=)\d+' "$out.summary"|head -1)" "$l0" "$(cut -d' ' -f1 /proc/loadavg)" \
    "$fa0" "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader|grep -c "$GPU_UUID")" \
    "$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1)"
}

say "PHASE1 correctness trees"
for v in $TIMED $EDGE $F48; do for arm in base cand; do run_one "$arm" "$v" "$W/results/p4_${arm}__${v}"; done; done

say "PHASE2 selected frames and grouping, candidate"
$W/tools/selected_frames.sh "$CAND" "$GPU" fs4_cand
say "PHASE2b selected frames and grouping, base reference"
$W/tools/selected_frames.sh "$BASE" "$GPU" fs4_base

say "PHASE3 paired timed series, $REPEATS repeats"
for r in $(seq 1 "$REPEATS"); do
  for v in $TIMED; do
    if [ $(( r % 2 )) -eq 1 ]; then order="base cand"; else order="cand base"; fi
    for arm in $order; do
      out=$W/results/tmp4_${arm}__${v}
      echo "PAIR rep=$r order=${order// />}"
      run_one "$arm" "$v" "$out"; rm -rf "$out" "$out.summary"
    done
  done
done

say "PHASE4 host-to-device bytes per route (Nsight, one movie per arm)"
ALLV="$TIMED u16_lzw_rps1 $F48"
$W/tools/h2d_bytes.sh "$BASE" "$GPU" base $ALLV
$W/tools/h2d_bytes.sh "$CAND" "$GPU" cand $ALLV
say "CAMPAIGN_DONE"
