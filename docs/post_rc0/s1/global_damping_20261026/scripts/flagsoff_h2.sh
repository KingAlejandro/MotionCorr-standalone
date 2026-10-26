#!/bin/bash
# usage: flagsoff_h2.sh   (on cpu64) H2 binary, flags-off product identity, base e77a51a2 vs h2, on the known-motion fixtures
# (tools/run_known_motion_gates.py: j1, dose-weighted and j4 runs per case) and the repo synthetic movie.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
F=$DS_SC/flagsoff-h2; mkdir -p $F; R=$F/receipts; mkdir -p $R
# Products mirror the absolute input path (memory: motioncorr-output-path-mirrors-input-path), so both arms must read the
# synthetic movie from ONE shared path. Attempt 1 read it from src-base/ and src-h2/ and the trees differed only by that path.
SYN=$F/synth-input; mkdir -p $SYN; cp $DS_SC/src-h2/test-data/synthetic/synthetic_movie.tiff $SYN/
cmp $DS_SC/src-h2/test-data/synthetic/synthetic_movie.tiff $DS_SC/src-base/test-data/synthetic/synthetic_movie.tiff && echo "synthetic movie identical in both source trees" >> $R/rc.txt
for arm in base h2; do
  src=$DS_SC/src-$arm
  [ "${FLAGSOFF_ONLY:-all}" = synth ] || {
  lane $DS_PY -I $src/tools/run_known_motion_gates.py --binary $DS_SC/build-$arm/motioncorr --python $DS_PY --outdir $F/km-$arm --json $F/km-$arm.json > $R/km-$arm.out 2>&1
  echo "km-$arm rc=$?" | tee -a $R/rc.txt; }
  mkdir -p $F/synth-$arm
  lane $DS_SC/build-$arm/motioncorr --i $SYN/synthetic_movie.tiff --o $F/synth-$arm --use_own --j 1 --dose_weighting --dose_per_frame 1.0 --voltage 300 --angpix 1.0 --patch_x 3 --patch_y 3 --bfactor 150 > $R/synth-$arm.out 2>&1
  echo "synth-$arm rc=$?" | tee -a $R/rc.txt
done
for p in $( [ "${FLAGSOFF_ONLY:-all}" = synth ] && echo synth || echo km synth ); do
  lane $DS_PY -I $D/compare_products.py $F/$p-base $F/$p-h2 $F/$p-compare.json | tee -a $R/rc.txt
done
# Negative control: the H2 binary with the flag ON on the same movie must be seen as different by the same comparator.
mkdir -p $F/synth-h2-coupled
lane $DS_SC/build-h2/motioncorr --i $SYN/synthetic_movie.tiff --o $F/synth-h2-coupled --use_own --j 1 --dose_weighting --dose_per_frame 1.0 --voltage 300 --angpix 1.0 --patch_x 3 --patch_y 3 --bfactor 150 --experimental_coupled_peak global > $R/synth-h2-coupled.out 2>&1
echo "synth-h2-coupled rc=$?" | tee -a $R/rc.txt
lane $DS_PY -I $D/compare_products.py $F/synth-h2 $F/synth-h2-coupled $F/synth-negative-control.json --expect-differ | tee -a $R/rc.txt
