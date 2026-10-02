#!/bin/bash
# Campaign 8: host-stage breakdown with TIMING=ON.
#
# RCTIC/RCTOC compile to nothing without -DTIMING, so the production binaries
# measured in campaigns 4-5 are unaffected by the instrumentation; these are
# separate builds whose only purpose is the stage split. Their wall times are
# NOT comparable with the production ones and are not reported as such.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
say() { echo "[$(date -u +%FT%TZ)] $*"; }
say "BUILD TIMING arms"
taskset -c $MASK $W/tools/build.sh $W/src-base   $W/bld-base-t -DTIMING=ON || { say FATAL; exit 1; }
taskset -c $MASK $W/tools/build.sh $W/src-u8b-t  $W/bld-u8-t   -DTIMING=ON || { say FATAL; exit 1; }
GPU=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")" -eq 0 ] && { GPU=$idx; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no free GPU"; exit 1; }
BASE=$W/bld-base-t/motioncorr; CAND=$W/bld-u8-t/motioncorr
say "TARGET gpu=$GPU base=$(sha256sum $BASE|cut -c1-16) cand=$(sha256sum $CAND|cut -c1-16)"

VARS="u16_deflate_rps1 u8_lzw_rps1 u8_deflate_rps1 u16_deflate_rps8 u16_lzw_rps1 u8_lzw_rps1_48f u8_deflate_rps1_48f"
for rep in 1 2 3; do
for v in $VARS; do
  for arm in base cand; do
    [ "$arm" = base ] && bin=$BASE || bin=$CAND
    out=$W/results/t_${arm}__${v}
    taskset -c $MASK $W/tools/run_matrix.sh "$bin" "$W/inputs/$v" "$out" "$GPU" > "$out.summary" 2>&1
    echo "STAGEHDR rep=$rep arm=$arm variant=$v rc=$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1) routes=[$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1|tr -s ' ')]"
    # The timing report goes to stdout at the end of the run.
    awk '/^ *[A-Za-z].*: +[0-9.]+ sec/ {print "STAGE rep='"$rep"' arm='"$arm"' variant='"$v"' " $0}' "$out.stdout"
    rm -rf "$out" "$out.summary" "$out.witness" "$out.stdout" "$out.time"
  done
done
done
say "CAMPAIGN_DONE"
