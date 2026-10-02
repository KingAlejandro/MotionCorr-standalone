#!/bin/bash
# Multi-row and uint8 nvCOMP arms, against a binary built inside this lock
# acquisition from the fixed source. Campaign 2 measured a binary whose
# frame-stage sizing walked ny strips instead of strips_per_frame, which
# declined every multi-row movie before the decoder was reached.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
TIMED="u16_deflate_rps1 u16_deflate_rps8 u8_deflate_rps1"
EDGE="u16_deflate_rps2 u16_deflate_rps512 u8_deflate_rps16 u8_lzw_rps64 u16_deflate_pred2 u16_raw_rps1 u16_lzw_rps1 u8_lzw_rps1"
REPEATS=${REPEATS:-5}
say() { echo "[$(date -u +%FT%TZ)] $*"; }

say "BUILD candidate from src-u8b"
taskset -c $MASK $W/tools/build.sh $W/src-u8b $W/bld-u8b || { say "FATAL build"; exit 1; }

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
BASE=$W/bld-base/motioncorr; CAND=$W/bld-u8b/motioncorr
say "BINARIES base=$(sha256sum $BASE|cut -c1-16) cand=$(sha256sum $CAND|cut -c1-16)"

say "CTEST on the candidate build"
(cd $W/bld-u8b && taskset -c $MASK ctest --output-on-failure -j1 > $W/logs/ctest-u8b.log 2>&1; echo "CTEST rc=$?")
tail -3 $W/logs/ctest-u8b.log | sed 's/^/    /'

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

say "PHASE1 correctness trees, fixed candidate"
for v in $TIMED $EDGE; do for arm in base cand; do run_one "$arm" "$v" "$W/results/p3_${arm}__${v}"; done; done

say "PHASE2b selected frames and grouping, candidate"
$W/tools/selected_frames.sh "$CAND" "$GPU" fs_cand
say "PHASE2c selected frames and grouping, base reference"
$W/tools/selected_frames.sh "$BASE" "$GPU" fs_base

say "PHASE3 paired timed series, $REPEATS repeats"
for r in $(seq 1 "$REPEATS"); do
  for v in $TIMED; do
    if [ $(( r % 2 )) -eq 1 ]; then order="base cand"; else order="cand base"; fi
    for arm in $order; do
      out=$W/results/tmp3_${arm}__${v}
      echo "PAIR rep=$r order=${order// />}"
      run_one "$arm" "$v" "$out"; rm -rf "$out" "$out.summary"
    done
  done
done
say "CAMPAIGN_DONE"
