#!/bin/bash
# Locate the fast-versus-exact difference (docs/fft_size_policy.md, Diagnosis).
# build-diag is this branch plus a scratch MC_FFT_DIAG switch in
# CudaMovieSession::setFftSizePolicyFast: "frames" pads frames only (global
# alignment, shifted inverse, dose weighting), "patches" pads patches only
# (fft_size_policy/diag/diag_switch.diff, applied to a copy of src).
set -u
ARMS="${*:-gpu fast frames patches cpu}"  # rerun a subset: diag.sh frames patches
W=/home/alex/mc-fft; V=$W/diag; L=$V/diag.txt; PY=/home/alex/.mc-venv/bin/python
S=$W/src/docs/fft_size_policy/scripts
mkdir -p $V; : >> $L
BIN=$W/build/motioncorr; DIAG=$W/build-diag/motioncorr
GPU3=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
D=/home/alex/mc-perf-20261001/data
OPTS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --save_noDW"
run() { # arm env bin args...
  local arm=$1 e=$2 bin=$3; shift 3; local o=$V/out/$arm; rm -rf $o; mkdir -p $o
  ( cd $D && flock /tmp/motioncorr-gpu3-correctness.lock env $e CUDA_VISIBLE_DEVICES=$GPU3 taskset -c 80-87 \
      /usr/bin/time -v $bin --i movies.star --o $o/ $OPTS "$@" > $V/$arm.stdout 2> $V/$arm.time )
  echo "$arm rc=$? n_mrc=$(ls $o/Movies/*.mrc 2>/dev/null | wc -l) $(grep -h 'FFT size policy fast' $o/Movies/*.log | sort | uniq -c | head -1)" >> $L
}
echo "load: $(cat /proc/loadavg)" >> $L
has() { [[ " $ARMS " == *" $1 "* ]]; }
has gpu     && run gpu     MC_FFT_DIAG= $BIN  --gpu 0 --ingest nvcomp
has fast    && run fast    MC_FFT_DIAG= $BIN  --gpu 0 --ingest nvcomp --fft_size_policy fast
has frames  && run frames  MC_FFT_DIAG=frames  $DIAG --gpu 0 --ingest nvcomp --fft_size_policy fast
has patches && run patches MC_FFT_DIAG=patches $DIAG --gpu 0 --ingest nvcomp --fft_size_policy fast
has cpu     && run cpu     MC_FFT_DIAG= $BIN
cmpv() { echo "== $1 -> $2" >> $L; $PY $S/validate_compare.py $V/out/$1 $V/out/$2 --test-log $V/$2.time --json-out $V/$1_vs_$2.json >> $L 2>&1; }
emap() { echo "== errmap $1 -> $2" >> $L; $PY $S/errmap.py $V/out/$1 $V/out/$2 --json-out $V/err_$1_vs_$2.json \
  --map-movie 20170629_00021_frameImage --map-out $V/map_$1_vs_$2.pgm >> $L 2>&1; }
for a in gpu fast frames patches; do has $a && cmpv cpu $a; done
for a in fast frames patches; do has $a && cmpv gpu $a; done
has gpu && emap cpu gpu; for a in fast frames patches; do has $a && emap gpu $a; done
echo DIAG-DONE >> $L
