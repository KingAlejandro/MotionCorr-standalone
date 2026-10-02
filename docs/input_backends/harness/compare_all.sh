#!/bin/bash
# Product identity: (a) base vs candidate per variant, (b) every variant against
# the uint16 Deflate reference. (b) is the strong gate: the variants hold the
# same sample values, so a correct route must produce the same products.
set -u
W=/home/alex/mc-inputs-20261002
PY=$HOME/.mc-venv/bin/python
CMP="$PY $W/tools/compare_output_trees.py"
M6=$W/tools/six_movie_manifest.json
M2=$W/tools/two_movie_manifest.json
TIMED="u16_deflate_rps1 u8_lzw_rps1 u8_deflate_rps1 u16_lzw_rps1 u16_deflate_rps8"
EDGE="u16_deflate_rps2 u16_deflate_rps512 u8_deflate_rps16 u8_lzw_rps64 u16_deflate_pred2 u16_raw_rps1"

verdict() { # label base cand manifest star
  local out
  local rc
  out=$($CMP "$2" "$3" --manifest "$4" --input-star "$5" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo "$1 PASS  $(echo "$out" | grep -o 'Validated.*pixels per arm')"
  else echo "$1 FAIL"; echo "$out" | tail -6 | sed 's/^/      /'; fi
}

echo "### (a) base vs candidate, same variant"
for v in $TIMED; do verdict "$v" "$W/results/p1_base__$v" "$W/results/p1_cand__$v" "$M6" "$W/inputs/$v/movies.star"; done
for v in $EDGE;  do verdict "$v" "$W/results/p1_base__$v" "$W/results/p1_cand__$v" "$M2" "$W/inputs/$v/movies.star"; done

echo "### (b) every candidate variant vs the uint16 Deflate reference (6-movie)"
REF=$W/results/p1_cand__u16_deflate_rps1
for v in u8_lzw_rps1 u8_deflate_rps1 u16_lzw_rps1 u16_deflate_rps8; do
  verdict "ref-vs-$v" "$REF" "$W/results/p1_cand__$v" "$M6" "$W/inputs/$v/movies.star"
done
echo "### (c) every candidate edge variant vs the 2-movie uint16 Deflate reference"
for v in $EDGE; do
  verdict "ref2-vs-$v" "$W/results/p1_cand__u16_deflate_rps2" "$W/results/p1_cand__$v" "$M2" "$W/inputs/$v/movies.star"
done
