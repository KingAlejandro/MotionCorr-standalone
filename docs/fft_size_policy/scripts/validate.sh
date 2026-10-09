#!/bin/bash
# Numerical validation of --fft_size_policy fast, 24 tutorial movies + known-motion gates, 4GPUs GPU3.
set -u
W=/home/alex/mc-fft; V=$W/val; L=$V/validate.txt; PY=/home/alex/.mc-venv/bin/python
S=$W/src/docs/fft_size_policy/scripts
mkdir -p $V; : > $L
BIN=$W/build/motioncorr; MUT=$W/build/motioncorr_fft_dw_mutant
GPU3=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
D=/home/alex/mc-perf-20261001/data
OPTS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --save_noDW"
run() { # arm bin args...
  local arm=$1 bin=$2; shift 2; local o=$V/out/$arm; rm -rf $o; mkdir -p $o
  ( cd $D && flock /tmp/motioncorr-gpu3-correctness.lock env CUDA_VISIBLE_DEVICES=$GPU3 taskset -c 80-87 \
      /usr/bin/time -v $bin --i movies.star --o $o/ $OPTS "$@" > $V/$arm.stdout 2> $V/$arm.time )
  echo "$arm rc=$? n_mrc=$(ls $o/Movies/*.mrc 2>/dev/null | wc -l)" >> $L
}
echo "load: $(cat /proc/loadavg)" >> $L
run gpu  $BIN --gpu 0 --ingest nvcomp
run fast $BIN --gpu 0 --ingest nvcomp --fft_size_policy fast
run mut  $MUT --gpu 0 --ingest nvcomp --fft_size_policy fast
run cpu  $BIN
cmpv() { echo "== $1 -> $2" >> $L; $PY $S/validate_compare.py $V/out/$1 $V/out/$2 --test-log $V/$2.time --json-out $V/$1_vs_$2.json >> $L 2>&1; }
cmpv cpu gpu; cmpv cpu fast; cmpv gpu fast; cmpv fast mut; cmpv cpu mut
# Known-motion gates (#60 calibrated thresholds), default and fast.
printf '#!/bin/sh\nexec %s "$@" --fft_size_policy fast\n' $BIN > $V/motioncorr_fast; chmod +x $V/motioncorr_fast
printf '#!/bin/sh\nexec %s "$@" --fft_size_policy fast\n' $MUT > $V/motioncorr_mut; chmod +x $V/motioncorr_mut
for arm in default fast mut; do
  b=$BIN; [ $arm = fast ] && b=$V/motioncorr_fast; [ $arm = mut ] && b=$V/motioncorr_mut
  rm -rf $V/km_$arm
  ( cd $W/src && flock /tmp/motioncorr-gpu3-correctness.lock env CUDA_VISIBLE_DEVICES=$GPU3 taskset -c 80-87 \
      $PY tools/run_known_motion_gates.py --binary $b --python $PY --gpu 0 --outdir $V/km_$arm \
      --fixtures $W/km_fixtures --include-heavy --json $V/km_$arm.json > $V/km_$arm.txt 2>&1 )
  echo "known-motion $arm rc=$? $(tail -1 $V/km_$arm.txt)" >> $L
done
echo VALIDATE-DONE >> $L
