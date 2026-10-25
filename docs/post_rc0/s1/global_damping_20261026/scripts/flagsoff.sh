#!/bin/bash
# usage: flagsoff.sh   (on cpu64) Flags-off product identity, base e77a51a2 vs cand, on the known-motion fixtures
# (tools/run_known_motion_gates.py: j1, dose-weighted and j4 runs per case) and the repo synthetic movie.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
F=$DS_SC/flagsoff; mkdir -p $F; R=$F/receipts; mkdir -p $R
for arm in base cand; do
  src=$DS_SC/src-$arm
  lane $DS_PY -I $src/tools/run_known_motion_gates.py --binary $DS_SC/build-$arm/motioncorr --python $DS_PY --outdir $F/km-$arm --json $F/km-$arm.json > $R/km-$arm.out 2>&1
  echo "km-$arm rc=$?" | tee -a $R/rc.txt
  mkdir -p $F/synth-$arm
  lane $DS_SC/build-$arm/motioncorr --i $src/test-data/synthetic/synthetic_movie.tiff --o $F/synth-$arm --use_own --j 1 --dose_weighting --dose_per_frame 1.0 --voltage 300 --angpix 1.0 --patch_x 3 --patch_y 3 --bfactor 150 > $R/synth-$arm.out 2>&1
  echo "synth-$arm rc=$?" | tee -a $R/rc.txt
done
for p in km synth; do
  lane $DS_PY -I $D/compare_products.py $F/$p-base $F/$p-cand $F/$p-compare.json | tee -a $R/rc.txt
done
