#!/bin/bash
# Second-pass oracle for series.sh (products only: .log carries timings, _shifts.eps draws its own path).
# launcher's merged dir: it inventories every STAR, so the _workers/ staging dir is
# excluded, and the joint STAR's absolute arm path is rewritten to the copy's own path.
set -uo pipefail
D=/home/alex/mc-wpdf-20261013
DATA=/home/alex/MotionCorr-standalone/relion30_tutorial
PY=/home/alex/.mc-venv/bin/python3
CMPT="$PY $D/src-cand/docs/issue85_laneC/compare_output_trees.py"
MAN="--manifest $D/src-cand/docs/issue85_laneC/tutorial_24_movie_manifest.json --input-star $DATA/movies.star"
cd $D; rm -rf cmp; mkdir cmp
for n in base cand; do
  rsync -a --exclude=_workers runs/$n/merged/ cmp/$n/
  find cmp/$n -type f \( -name '*.star' -o -name '*.lst' \) -exec sed -i "s|$D/runs/$n/merged|$D/cmp/$n|g" {} +
done
cp -a cmp/cand cmp/ctl; find cmp/ctl -type f \( -name "*.star" -o -name "*.lst" \) -exec sed -i "s|$D/cmp/cand|$D/cmp/ctl|g" {} +
# control: one payload byte of one corrected micrograph flipped
f=cmp/ctl/Movies/20170629_00021_frameImage.mrc
$PY -c "import sys;p=sys.argv[1];b=bytearray(open(p,'rb').read());b[-4096]^=1;open(p,'wb').write(b)" $f
for pair in "base cand treat" "base ctl ctl-mrc-payload-flip"; do
  set -- $pair
  echo "--- $3: $1 vs $2"
  $CMPT cmp/$1 cmp/$2 $MAN --products-only --json-out cmp/$3.json 2>&1 | tail -3
  echo "rc=${PIPESTATUS[0]}"
done
echo "=== worker console lines 'Now generating logfile.pdf' (count per worker) ==="
for n in base cand; do for w in runs/$n/workers/w*; do
  echo "$n $(basename $w) $(grep -c 'Now generating logfile.pdf' $w/launcher.console.log)"; done; done
echo CMP_DONE
