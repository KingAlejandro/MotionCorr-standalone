#!/bin/bash
# Issue 61 Stage A: CTFFIND 4.1 fit on each arm's corrected micrographs.
set -u
ROOT=/home/alex/mc-issue61
BIN=/home/alex/relion-container-tests/bin/relion-container-bin-r2
ARMS="${ARMS:-cpu default allfftw ctrl_noise_f005 ctrl_noise_f020 ctrl_envelope_b20}"
for arm in $ARMS; do
  P=$ROOT/proj/$arm
  cd "$P" || exit 1
  # clean input micrograph STAR: optics table verbatim from the tutorial project + our micrographs
  {
    printf '\n# version 30001\n\ndata_optics\n\nloop_ \n'
    printf '_rlnOpticsGroupName #1 \n_rlnOpticsGroup #2 \n_rlnMtfFileName #3 \n'
    printf '_rlnMicrographOriginalPixelSize #4 \n_rlnVoltage #5 \n_rlnSphericalAberration #6 \n'
    printf '_rlnAmplitudeContrast #7 \n_rlnMicrographPixelSize #8 \n'
    printf 'opticsGroup1            1 mtf_k2_200kV.star     0.885000   200.000000     1.400000     0.100000     0.885000 \n \n'
    printf '\n# version 30001\n\ndata_micrographs\n\nloop_ \n_rlnMicrographName #1 \n_rlnOpticsGroup #2 \n'
    for m in MotionCorr/job002/Movies/*.mrc; do printf '%s            1 \n' "$m"; done
  } > mics.star
  rm -rf CtfFind61
  /usr/bin/time -v $BIN/relion_run_ctffind \
      --i mics.star --o CtfFind61/ \
      --Box 512 --ResMin 30 --ResMax 5 --dFMin 5000 --dFMax 50000 \
      --FStep 500 --dAst 100 --ctffind_exe $BIN/ctffind --ctfWin -1 \
      --is_ctffind4 --fast_search --j 8 \
      > $ROOT/logs/ctffind_$arm.log 2> $ROOT/logs/ctffind_$arm.time
  echo "$arm rc=$? $(grep -m1 'Elapsed (wall clock)' $ROOT/logs/ctffind_$arm.time | awk '{print $NF}') n=$(grep -c frameImage CtfFind61/micrographs_ctf.star 2>/dev/null)"
done
echo STAGE_A_DONE
