#!/bin/bash
# Selected frames and grouping, across the three routes.
#
# The route must not change which frames are used, how they are numbered or
# what the dose weighting does. Each option set runs on the uint16 Deflate
# reference and on the two uint8 variants, which hold identical sample values,
# so all three product trees must be identical.
#
# Comparison goes through cmp_trees.sh, which declares the ingest route's own
# log lines. Without that declaration every cross-route comparison fails on
# six .log files while every MRC and STAR is identical -- a verdict that says
# nothing about products.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
BIN=$1; GPU=$2; TAG=$3
REF=u16_deflate_rps1
VARS="u8_lzw_rps1 u8_deflate_rps1"
NAMES="all first3 last20 sub3to20 group2 group5 mixed"
opts_for() {
  case $1 in
    all) echo "" ;;
    first3) echo "--first_frame_sum 3" ;;
    last20) echo "--last_frame_sum 20" ;;
    sub3to20) echo "--first_frame_sum 3 --last_frame_sum 20" ;;
    group2) echo "--group_frames 2" ;;
    group5) echo "--group_frames 5" ;;
    mixed) echo "--first_frame_sum 2 --last_frame_sum 21 --group_frames 4" ;;
  esac
}
for o in $NAMES; do
  O=$(opts_for "$o")
  rout=$W/results/${TAG}_${o}__$REF
  taskset -c $MASK $W/tools/run_matrix.sh "$BIN" "$W/inputs/$REF" "$rout" "$GPU" $O > "$rout.summary" 2>&1
  rrc=$(grep -oP '(?<=^RC=)\d+' "$rout.summary"|head -1)
  rroutes=$(grep -oP '(?<=^ROUTES=).*' "$rout.summary"|head -1 | tr -s ' ')
  for v in $VARS; do
    out=$W/results/${TAG}_${o}__${v}
    taskset -c $MASK $W/tools/run_matrix.sh "$BIN" "$W/inputs/$v" "$out" "$GPU" $O > "$out.summary" 2>&1
    printf 'FRAMESEL2 tag=%s opts=%-10s ref_rc=%s ref_routes=[%s] variant=%-16s rc=%s routes=[%s]\n' \
      "$TAG" "$o" "$rrc" "$rroutes" "$v" \
      "$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1)" \
      "$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1 | tr -s ' ')"
    $W/tools/cmp_trees.sh "FRAMESEL2 $TAG $o $v vs ref" "$rout" "$out" \
      $W/tools/six_movie_manifest.json $W/inputs/$v/movies.star
    rm -rf "$out" "$out.summary" "$out.witness" "$out.stdout" "$out.time"
  done
  rm -rf "$rout" "$rout.summary" "$rout.witness" "$rout.stdout" "$rout.time"
done
