#!/bin/bash
# Issue 61 Stage C: normal (unmatched) auto-refinement workflow, one arm at a time.
# Identical command, reference, particles, mask and settings in every arm; only
# the corrected micrographs behind the extracted particles differ.
set -u
ROOT=/home/alex/mc-issue61
BIN=/home/alex/relion-container-tests/bin/relion-container-bin-r2
PRE=/home/alex/relion-container-tests/data/spa-relion50-precalculated/extracted
SET=${SET:-held22}
for arm in ${ARMS:-cpu default allfftw}; do
  P=$ROOT/proj/$arm; cd "$P" || exit 1
  rm -rf Refine61_$SET; mkdir -p Refine61_$SET
  /usr/bin/time -v $BIN/relion_refine \
    --o Refine61_$SET/run --auto_refine --split_random_halves \
    --i $ROOT/stars/$arm/$SET.star \
    --ref $PRE/Class3D/job016/run_it025_class002_box256.mrc \
    --firstiter_cc --ini_high 50 --dont_combine_weights_via_disc --preread_images \
    --pool 30 --pad 1 --auto_ignore_angles --auto_resol_angles --ctf \
    --particle_diameter 200 --flatten_solvent --zero_mask --oversampling 1 \
    --healpix_order 2 --auto_local_healpix_order 4 --offset_range 5 --offset_step 2 \
    --sym D2 --low_resol_join_halves 40 --norm --scale --j 8 --gpu "0:1:2:3" \
    > $ROOT/logs/refine_${arm}_$SET.log 2> $ROOT/logs/refine_${arm}_$SET.time
  rc=$?
  echo "refine $arm rc=$rc $(grep -m1 'Elapsed (wall clock)' $ROOT/logs/refine_${arm}_$SET.time|awk '{print $NF}')"
  if [ -f Refine61_$SET/run_half1_class001_unfil.mrc ]; then
    $BIN/relion_postprocess --i $P/Refine61_$SET/run_half1_class001_unfil.mrc \
      --o $ROOT/pp/$arm/refine_$SET --mask MaskCreate/job020/mask.mrc \
      --angpix 1.244531 --mtf mtf_k2_200kV.star --mtf_angpix 0.885 \
      --auto_bfac --autob_lowres 10 > $ROOT/logs/pp_refine_${arm}_$SET.log 2>&1
    echo "  postprocess rc=$? res=$(grep -m1 _rlnFinalResolution $ROOT/pp/$arm/refine_$SET.star|awk '{print $2}')"
  else
    echo "  NO HALF MAP - refinement did not complete"
  fi
done
echo STAGE_C_DONE
