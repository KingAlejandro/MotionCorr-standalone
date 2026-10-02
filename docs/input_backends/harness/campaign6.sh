#!/bin/bash
# Campaign 6: the pinned-route contract, and the Nsight byte/time post-process.
#
# --ingest {nvcomp,compact,float} must fail a movie that cannot take the named
# route rather than silently using another. That is the contract the route
# matrix depends on: without it, "this variant took nvcomp" is an observation
# about defaults, not about eligibility.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
say() { echo "[$(date -u +%FT%TZ)] $*"; }
GPU=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")" -eq 0 ] && { GPU=$idx; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no free GPU"; exit 1; }
BASE=$W/bld-baseb/motioncorr; CAND=$W/bld-u8c/motioncorr
say "TARGET gpu=$GPU cand=$(sha256sum $CAND|cut -c1-16)"

say "PHASE G pinned-route contract"
VARS="u16_deflate_rps1 u16_deflate_rps8 u16_deflate_rps512 u16_lzw_rps1 u16_deflate_pred2 u16_raw_rps1 u8_deflate_rps1 u8_deflate_rps16 u8_lzw_rps1 u8_lzw_rps3837"
for v in $VARS; do
  line="$v"
  for mode in nvcomp compact float; do
    out=$W/results/pin_${mode}__${v}
    taskset -c $MASK $W/tools/run_matrix.sh "$CAND" "$W/inputs/$v" "$out" "$GPU" --ingest $mode > "$out.summary" 2>&1
    rc=$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1)
    rt=$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1 | tr -s ' ' | sed 's/^ //;s/ $//')
    if [ "${rc:-1}" = 0 ]; then line="$line  $mode=OK[$rt]"; else line="$line  $mode=REFUSED"; fi
    rm -rf "$out" "$out.summary" "$out.witness" "$out.stdout" "$out.time"
  done
  echo "PINNED $line"
done

say "PHASE H Nsight host-to-device bytes and time"
$PY $W/tools/h2d_report.py $W/results
say "CAMPAIGN_DONE"
