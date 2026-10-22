#!/bin/bash
# #267 eight known-motion cases on the C1 binaries, CPU and CUDA(+nvCOMP), arm 'unset' (no MC_DIAG_*). usage: c1_v2.sh cpu|cuda
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
be=$1; V=$C1_SCR/v2; S=$C1_SCR/src; T=$S/docs/post_rc0/s1/synth_combined
mkdir -p $V
[ -d $V/v2fixtures ] || $C1_PY $S/test-data/generate_motion_diagnostics.py --outdir $V/v2fixtures > $V/generate.log 2>&1 || exit 2
if [ "$be" = cpu ]; then
  $C1_PY -I $T/run_v2_cases.py $V cpu-unset cpu $C1_SCR/build-cpu/motioncorr unset $C1_CPUS || exit 3
else
  exec 9>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 lock contended; stopping"; exit 5; }
  "$(dirname "$0")/c1_occupancy.sh" v2-pre || exit 3
  $C1_PY -I $T/run_v2_cases.py $V cuda-unset cuda $C1_SCR/build-nvcomp/motioncorr unset $C1_CPUS $C1_GPU_UUID; rc=$?
  "$(dirname "$0")/c1_occupancy.sh" v2-post
  [ $rc -eq 0 ] || exit 3
fi
$C1_PY -I $T/eval_v2.py $V/v2fixtures $V/$be-unset $V/$be-unset.eval.json
