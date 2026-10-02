#!/bin/bash
# Selected frames and grouping, across the three routes.
#
# The route must not change which frames are used, how they are numbered or
# what the dose weighting does. Each option set runs on the uint16 Deflate
# reference (nvcomp), the uint8 LZW variant (compact) and the uint8 Deflate
# variant (nvcomp after the widening). The three variants hold identical
# sample values, so all three product trees must be identical; the comparison
# runs immediately and the trees are then deleted, so disk stays bounded.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
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
  rroutes=$(grep -oP '(?<=^ROUTES=).*' "$rout.summary"|head -1)
  for v in $VARS; do
    out=$W/results/${TAG}_${o}__${v}
    taskset -c $MASK $W/tools/run_matrix.sh "$BIN" "$W/inputs/$v" "$out" "$GPU" $O > "$out.summary" 2>&1
    rc=$(grep -oP '(?<=^RC=)\d+' "$out.summary"|head -1)
    routes=$(grep -oP '(?<=^ROUTES=).*' "$out.summary"|head -1)
    cmpout=$($PY $W/tools/compare_output_trees.py "$rout" "$out" \
               --manifest $W/tools/six_movie_manifest.json \
               --input-star $W/inputs/$v/movies.star 2>&1)
    if [ $? -eq 0 ]; then verdict=PASS; else verdict=FAIL; fi
    printf 'FRAMESEL tag=%s opts=%-10s ref_rc=%s ref_routes=[%s] variant=%-16s rc=%s routes=[%s] vs_ref=%s\n' \
      "$TAG" "$o" "$rrc" "$rroutes" "$v" "$rc" "$routes" "$verdict"
    [ "$verdict" = FAIL ] && echo "$cmpout" | tail -8 | sed 's/^/      /'
    rm -rf "$out" "$out.summary"
  done
  rm -rf "$rout" "$rout.summary"
done
