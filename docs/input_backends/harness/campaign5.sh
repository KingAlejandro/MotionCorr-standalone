#!/bin/bash
# Campaign 5: the gates campaign 4 could not read, plus the startup probe.
#
# Campaign 4's cross-variant comparisons failed on declared differences only --
# the route's own log line, and three harness files the runner wrapper wrote
# inside the product tree. Both are fixed: the wrapper writes its files beside
# the tree, and the route log lines are declared to the comparator, which drops
# them from BOTH arms so the allowance cannot hide a product difference.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
PY=$HOME/.mc-venv/bin/python
M6=$W/tools/six_movie_manifest.json
M2=$W/tools/two_movie_manifest.json
say() { echo "[$(date -u +%FT%TZ)] $*"; }

GPU=""; GPU_UUID=""
while read -r idx uuid; do
  idx=${idx%,}; uuid=${uuid%,}
  [ "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$uuid")" -eq 0 ] && { GPU=$idx; GPU_UUID=$uuid; break; }
done < <(nvidia-smi --query-gpu=index,uuid --format=csv,noheader)
[ -z "$GPU" ] && { say "FATAL no free GPU"; exit 1; }
BASE=$W/bld-baseb/motioncorr; CAND=$W/bld-u8c/motioncorr
say "TARGET gpu=$GPU uuid=$GPU_UUID base=$(sha256sum $BASE|cut -c1-16) cand=$(sha256sum $CAND|cut -c1-16)"

say "PHASE A product identity over the retained campaign-4 trees"
# Harness files written inside the tree by the previous wrapper revision.
find $W/results -maxdepth 2 \( -name route_witness.txt -o -name run.stdout -o -name run.time \) -delete
SIX="u16_deflate_rps1 u8_lzw_rps1 u8_deflate_rps1 u16_deflate_rps8 u16_lzw_rps1"
TWO="u16_deflate_rps2 u16_deflate_rps512 u8_deflate_rps16 u8_lzw_rps64 u16_deflate_pred2 u16_raw_rps1"
F48="u16_deflate_rps1_48f u8_lzw_rps1_48f u8_deflate_rps1_48f"
echo "--- base vs candidate, same variant ---"
for v in $SIX; do $W/tools/cmp_trees.sh "base-vs-cand $v" $W/results/p4_base__$v $W/results/p4_cand__$v $M6 $W/inputs/$v/movies.star; done
for v in $TWO $F48; do $W/tools/cmp_trees.sh "base-vs-cand $v" $W/results/p4_base__$v $W/results/p4_cand__$v $M2 $W/inputs/$v/movies.star; done
echo "--- candidate: every variant against the uint16 Deflate reference ---"
for v in u8_lzw_rps1 u8_deflate_rps1 u16_deflate_rps8 u16_lzw_rps1; do
  $W/tools/cmp_trees.sh "ref-vs-$v" $W/results/p4_cand__u16_deflate_rps1 $W/results/p4_cand__$v $M6 $W/inputs/$v/movies.star; done
for v in $TWO; do
  $W/tools/cmp_trees.sh "ref2-vs-$v" $W/results/p4_cand__u16_deflate_rps2 $W/results/p4_cand__$v $M2 $W/inputs/$v/movies.star; done
for v in u8_lzw_rps1_48f u8_deflate_rps1_48f; do
  $W/tools/cmp_trees.sh "ref48-vs-$v" $W/results/p4_cand__u16_deflate_rps1_48f $W/results/p4_cand__$v $M2 $W/inputs/$v/movies.star; done
echo "--- base: the same cross-format identity on main, as a positive control ---"
for v in u8_lzw_rps1 u8_deflate_rps1; do
  $W/tools/cmp_trees.sh "base-ref-vs-$v" $W/results/p4_base__u16_deflate_rps1 $W/results/p4_base__$v $M6 $W/inputs/$v/movies.star; done

say "PHASE B negative control: the comparator must reject a real product difference"
CTL=$W/results/ctl_mutated
rm -rf $CTL; cp -a $W/results/p4_cand__u8_lzw_rps1 $CTL
$PY - "$CTL" <<'EOF'
import sys, glob, struct
# Flip one pixel of one corrected image: invisible to a file inventory, and the
# smallest difference the pixel comparison is supposed to catch.
p = sorted(glob.glob(sys.argv[1] + "/Movies/*.mrc"))[0]
with open(p, "r+b") as f:
    f.seek(1024)
    v, = struct.unpack("<f", f.read(4))
    f.seek(1024); f.write(struct.pack("<f", v + 1.0))
print("mutated first pixel of", p, v, "->", v + 1.0)
EOF
sed -i "s|$W/results/p4_cand__u8_lzw_rps1|$CTL|g" $CTL/corrected_micrographs.star
$W/tools/cmp_trees.sh "NEGATIVE-CONTROL one-pixel mutation (must FAIL)" \
  $W/results/p4_cand__u16_deflate_rps1 $CTL $M6 $W/inputs/u8_lzw_rps1/movies.star
rm -rf $CTL

say "PHASE C selected frames and grouping"
$W/tools/selected_frames.sh "$CAND" "$GPU" fs5_cand
$W/tools/selected_frames.sh "$BASE" "$GPU" fs5_base

say "PHASE D process startup cost, one movie, 7 reps alternating"
for r in $(seq 1 7); do
  if [ $(( r % 2 )) -eq 1 ]; then order="base cand"; else order="cand base"; fi
  for arm in $order; do
    [ "$arm" = base ] && bin=$BASE || bin=$CAND
    out=$W/results/start_${arm}
    rm -rf "$out"; mkdir -p "$out"
    ( cd $W/inputs/u16_deflate_rps1 && t0=$(date +%s.%N) && \
      taskset -c $MASK "$bin" --i movies1.star --o "$out/" --use_own --dose_weighting \
        --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 \
        --gainref Movies/gain.mrc --seed 1 --j 8 --gpu "$GPU" > "$out.stdout" 2>&1 && \
      t1=$(date +%s.%N) && \
      printf 'STARTUP rep=%d arm=%s order=%s process_s=%.3f movie_s=%s\n' "$r" "$arm" "${order// />}" \
        "$(echo "$t1 - $t0" | bc)" "$(grep -oP '(?<=Full movie wall time: )[0-9.]+' $out/Movies/*.log | head -1)" )
    rm -rf "$out" "$out.stdout"
  done
done
say "CAMPAIGN_DONE"
