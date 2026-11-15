#!/bin/bash
# usage: flagsoff_p1.sh   (on cpu64) Flags-off / DC-off product identity to e77a51a2 for the P1 builds:
#   p1off = default build (hook compiled out); p1on = hook built in, MC_EXPERIMENT_CCF_DC_ARM=none.
# Known-motion fixtures (tools/run_known_motion_gates.py) and the repo synthetic movie, products compared by compare_products.py.
# Negative controls: half gain ON (comparator sanity) and DC arm global ON (reported; not asserted to differ).
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
F=$DS_SC/flagsoff-p1; mkdir -p $F; R=$F/receipts; mkdir -p $R
SYN=$F/synth-input; mkdir -p $SYN; cp $DS_SC/src-p1/test-data/synthetic/synthetic_movie.tiff $SYN/
cmp $DS_SC/src-p1/test-data/synthetic/synthetic_movie.tiff $DS_SC/src-base/test-data/synthetic/synthetic_movie.tiff && echo "synthetic movie identical in both source trees" >> $R/rc.txt
ARGS="--use_own --j 1 --dose_weighting --dose_per_frame 1.0 --voltage 300 --angpix 1.0 --patch_x 3 --patch_y 3 --bfactor 150"
for v in base p1off p1on; do
  case $v in base) bin=$DS_SC/build-base/motioncorr; src=$DS_SC/src-base; dc=;; p1off) bin=$DS_SC/build-p1off/motioncorr; src=$DS_SC/src-p1; dc=;; p1on) bin=$DS_SC/build-p1on/motioncorr; src=$DS_SC/src-p1; dc=none;; esac
  [ -n "$dc" ] && export MC_EXPERIMENT_CCF_DC_ARM=$dc || unset MC_EXPERIMENT_CCF_DC_ARM
  lane $DS_PY -I $src/tools/run_known_motion_gates.py --binary $bin --python $DS_PY --outdir $F/km-$v --json $F/km-$v.json > $R/km-$v.out 2>&1
  echo "km-$v rc=$?" | tee -a $R/rc.txt
  mkdir -p $F/synth-$v
  lane $bin --i $SYN/synthetic_movie.tiff --o $F/synth-$v $ARGS > $R/synth-$v.out 2>&1
  echo "synth-$v rc=$?" | tee -a $R/rc.txt
done
unset MC_EXPERIMENT_CCF_DC_ARM
for v in p1off p1on; do for p in km synth; do
  lane $DS_PY -I $D/compare_products.py $F/$p-base $F/$p-$v $F/$p-base-vs-$v.json | tee -a $R/rc.txt
done; done
BIN=$DS_SC/build-p1on/motioncorr
mkdir -p $F/synth-p1on-half
MC_EXPERIMENT_CCF_DC_ARM=none lane $BIN --i $SYN/synthetic_movie.tiff --o $F/synth-p1on-half $ARGS --experimental_global_half_gain > $R/synth-p1on-half.out 2>&1
echo "synth-p1on-half rc=$?" | tee -a $R/rc.txt
lane $DS_PY -I $D/compare_products.py $F/synth-p1on $F/synth-p1on-half $F/synth-negative-control-half.json --expect-differ | tee -a $R/rc.txt
mkdir -p $F/synth-p1on-dcglobal
MC_EXPERIMENT_CCF_DC_ARM=global lane $BIN --i $SYN/synthetic_movie.tiff --o $F/synth-p1on-dcglobal $ARGS > $R/synth-p1on-dcglobal.out 2>&1
echo "synth-p1on-dcglobal rc=$?" | tee -a $R/rc.txt
lane $DS_PY -I $D/compare_products.py $F/synth-p1on $F/synth-p1on-dcglobal $F/synth-dcglobal-vs-none.json | tee -a $R/rc.txt
tail -2 $R/synth-p1on-dcglobal.out >> $R/rc.txt
# Capture ON (MC_DIAG_MODEL_OUT set) must not change products: same movie, hook build ARM=none, runtime file written beside the tree.
mkdir -p $F/synth-p1on-capture
MC_EXPERIMENT_CCF_DC_ARM=none MC_DIAG_MODEL_OUT=$F/synth-p1on-capture.runtime.json lane $BIN --i $SYN/synthetic_movie.tiff --o $F/synth-p1on-capture $ARGS > $R/synth-p1on-capture.out 2>&1
echo "synth-p1on-capture rc=$? runtime-file-bytes=$(wc -c < $F/synth-p1on-capture.runtime.json)" | tee -a $R/rc.txt
lane $DS_PY -I $D/compare_products.py $F/synth-p1on $F/synth-p1on-capture $F/synth-capture-vs-nocapture.json | tee -a $R/rc.txt
