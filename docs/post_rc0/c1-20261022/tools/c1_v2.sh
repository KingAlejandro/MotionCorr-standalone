#!/bin/bash
# #267 eight known-motion cases on the C1 binaries, CPU and CUDA(+nvCOMP), arm 'unset' (no MC_DIAG_*). usage: c1_v2.sh cpu|cuda
# CUDA: health pre-check stops the run; a failed post-check makes the wrapper exit 37.
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
be=$1; V=$C1_SCR/v2; S=$C1_SCR/src; T=$S/docs/post_rc0/s1/synth_combined
mkdir -p $V
[ -d $V/v2fixtures ] || $C1_PY $S/test-data/generate_motion_diagnostics.py --outdir $V/v2fixtures > $V/generate.log 2>&1 || exit 2
if [ "$be" = cpu ]; then
  $C1_PY -I $T/run_v2_cases.py $V cpu-unset cpu $C1_SCR/build-cpu/motioncorr unset $C1_CPUS || exit 3
  $C1_PY -I $T/eval_v2.py $V/v2fixtures $V/cpu-unset $V/cpu-unset.eval.json
  exit $?
fi
exec 9>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 lock contended; stopping"; exit 5; }
"$D/c1_occupancy.sh" v2-pre; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
$C1_PY -I $T/run_v2_cases.py $V cuda-unset cuda $C1_SCR/build-nvcomp/motioncorr unset $C1_CPUS $C1_GPU_UUID; rc=$?
[ $rc -eq 0 ] && { $C1_PY -I $T/eval_v2.py $V/v2fixtures $V/cuda-unset $V/cuda-unset.eval.json; rc=$?; }
"$D/c1_occupancy.sh" v2-post; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
