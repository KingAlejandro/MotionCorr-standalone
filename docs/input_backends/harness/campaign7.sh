#!/bin/bash
# Campaign 7: the frame-selection gate with a comparator that can read it.
set -u
W=/home/alex/mc-inputs-20261002
say() { echo "[$(date -u +%FT%TZ)] $*"; }
GPU=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")" -eq 0 ] && { GPU=$idx; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no free GPU"; exit 1; }
CAND=$W/bld-u8c/motioncorr; BASE=$W/bld-baseb/motioncorr
say "TARGET gpu=$GPU cand=$(sha256sum $CAND|cut -c1-16)"
say "PHASE C2 selected frames and grouping, candidate"
$W/tools/selected_frames2.sh "$CAND" "$GPU" fs7_cand
say "PHASE C2b selected frames and grouping, main"
$W/tools/selected_frames2.sh "$BASE" "$GPU" fs7_base
say "CAMPAIGN_DONE"
