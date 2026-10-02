#!/bin/bash
# Input-backends campaign v2. Everything runs inside one flock acquisition.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
# 6-movie variants: route, correctness and timing.
TIMED="u16_deflate_rps1 u8_lzw_rps1 u8_deflate_rps1 u16_lzw_rps1 u16_deflate_rps8"
# 2-movie variants: route and correctness only.
EDGE="u16_deflate_rps2 u16_deflate_rps512 u8_deflate_rps16 u8_lzw_rps64 u16_deflate_pred2 u16_raw_rps1"
REPEATS=${REPEATS:-5}
say() { echo "[$(date -u +%FT%TZ)] $*"; }

t0=$(date +%s)
while [ $(( $(pgrep -x cc1plus|wc -l)+$(pgrep -x nvcc|wc -l)+$(pgrep -x cicc|wc -l)+$(pgrep -x ptxas|wc -l) )) -gt 0 ]; do
  [ $(( $(date +%s) - t0 )) -ge 180 ] && break; sleep 5
done
say "SETTLE waited=$(( $(date +%s) - t0 ))s compilers=$(( $(pgrep -x cc1plus|wc -l)+$(pgrep -x nvcc|wc -l)+$(pgrep -x cicc|wc -l)+$(pgrep -x ptxas|wc -l) )) load1=$(cut -d' ' -f1 /proc/loadavg)"

GPU=""; GPU_UUID=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  n=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")
  [ "$n" -eq 0 ] && { GPU=$idx; GPU_UUID=$uuid; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no GPU free of foreign compute apps"; exit 1; }
say "TARGET gpu_index=$GPU uuid=$GPU_UUID"
BASE=$W/bld-base/motioncorr; CAND=$W/bld-u8/motioncorr
say "BINARIES base=$(sha256sum $BASE|cut -c1-16) cand=$(sha256sum $CAND|cut -c1-16)"

run_one() { # arm variant outdir
  local arm=$1 var=$2 out=$3 bin
  [ "$arm" = base ] && bin=$BASE || bin=$CAND
  local l0 fa0 t_start t_end
  l0=$(cut -d' ' -f1 /proc/loadavg)
  fa0=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$GPU_UUID")
  t_start=$(date +%s.%N)
  taskset -c $MASK $W/tools/run_matrix.sh "$bin" "$W/inputs/$var" "$out" "$GPU" > "$out.summary" 2>&1
  t_end=$(date +%s.%N)
  printf 'RESULT arm=%s variant=%s rc=%s elapsed=%.3f rss_kb=%s user_s=%s sys_s=%s products=%s load_pre=%s load_post=%s gpuapps=%s/%s routes=[%s]\n' \
    "$arm" "$var" "$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1)" \
    "$(echo "$t_end - $t_start"|bc)" \
    "$(grep -oP '(?<=Maximum resident set size \(kbytes\): )\d+' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=User time \(seconds\): ).*' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=System time \(seconds\): ).*' "$out.summary"|head -1)" \
    "$(grep -oP '(?<=^PRODUCTS=)\d+' "$out.summary"|head -1)" \
    "$l0" "$(cut -d' ' -f1 /proc/loadavg)" "$fa0" \
    "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader|grep -c "$GPU_UUID")" \
    "$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1)"
}

say "PHASE1 correctness trees (6-movie variants)"
for v in $TIMED; do for arm in base cand; do run_one "$arm" "$v" "$W/results/p1_${arm}__${v}"; done; done
say "PHASE1b correctness trees (2-movie edge variants)"
for v in $EDGE; do for arm in base cand; do run_one "$arm" "$v" "$W/results/p1_${arm}__${v}"; done; done

say "PHASE2 decoded-sample oracle (movie 00021 of every variant)"
for v in $TIMED $EDGE; do
  M=$W/inputs/$v/Movies/20170629_00021_frameImage.tiff
  [ -f "$M" ] || { echo "ORACLE variant=$v MISSING"; continue; }
  if taskset -c $MASK $W/tools/dump_native_samples "$M" /tmp/oracle.bin > /tmp/oracle.hdr 2>&1; then
    taskset -c $MASK $PY $W/tools/compare_native_samples.py "$M" /tmp/oracle.bin \
      --json "$W/results/oracle_${v}.json" > /dev/null 2>&1
    echo "ORACLE variant=$v verdict=$($PY -c "import json;d=json.load(open('$W/results/oracle_${v}.json'));print(d['verdict'],d['identity_vs_flipped_independent']['compared'],d['identity_vs_flipped_independent']['differing'],sorted(k for k,v in d['controls'].items() if k.endswith('_detected') and not v) or 'all-controls-fired')" 2>&1)"
  else
    echo "ORACLE variant=$v not-staged-by-compact-route: $(head -1 /tmp/oracle.hdr)"
  fi
  rm -f /tmp/oracle.bin
done

say "PHASE3 paired timed series, $REPEATS repeats"
for r in $(seq 1 "$REPEATS"); do
  for v in $TIMED; do
    if [ $(( r % 2 )) -eq 1 ]; then order="base cand"; else order="cand base"; fi
    for arm in $order; do
      out=$W/results/tmp_${arm}__${v}
      echo "PAIR rep=$r order=${order// />}"
      run_one "$arm" "$v" "$out"
      rm -rf "$out" "$out.summary"
    done
  done
done
say "CAMPAIGN_DONE"
