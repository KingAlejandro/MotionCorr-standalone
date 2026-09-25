#!/bin/bash
# Issue 61 Stage C (controlled): normal auto-refinement with an EXPLICIT random seed that is
# identical across arms, so the corrected micrographs are the only thing that differs.
# Repeated over several seeds so that seed-driven run-to-run variation can be separated from
# any between-arm difference.  Gold-standard --split_random_halves requires MPI; 1 master +
# 2 half-set workers x 3 threads = 7 of the 8 permitted CPUs.
set -u
ROOT=/home/alex/mc-issue61
BIN=/home/alex/relion-container-tests/bin/relion-container-bin-r2
SIF=/home/alex/relion-container-tests/sifs/relion-5.1.0-cuda12.8-sm80-full-plus-tomo-r2.sif
PRE=/home/alex/relion-container-tests/data/spa-relion50-precalculated/extracted
SET=${SET:-held22}
for seed in ${SEEDS:-61 62 63}; do
  for arm in ${ARMS:-cpu default allfftw}; do
    P=$ROOT/proj/$arm; cd "$P" || exit 1
    D=Refine61_${SET}_s${seed}
    rm -rf $D; mkdir -p $D
    /usr/bin/time -v apptainer exec --nv $SIF mpirun -n 3 \
      /opt/relion/bin/relion_refine_mpi \
      --o $D/run --auto_refine --split_random_halves --random_seed $seed \
      --i $ROOT/stars/$arm/$SET.star \
      --ref $PRE/Class3D/job016/run_it025_class002_box256.mrc \
      --firstiter_cc --ini_high 50 --dont_combine_weights_via_disc --preread_images \
      --pool 30 --pad 1 --auto_ignore_angles --auto_resol_angles --ctf \
      --particle_diameter 200 --flatten_solvent --zero_mask --oversampling 1 \
      --healpix_order 2 --auto_local_healpix_order 4 --offset_range 5 --offset_step 2 \
      --sym D2 --low_resol_join_halves 40 --norm --scale --j 3 --gpu "0,1:2,3" \
      > $ROOT/logs/refine_${arm}_${SET}_s${seed}.log 2> $ROOT/logs/refine_${arm}_${SET}_s${seed}.time
    rc=$?
    w=$(grep -m1 'Elapsed (wall clock)' $ROOT/logs/refine_${arm}_${SET}_s${seed}.time|awk '{print $NF}')
    if [ -f $D/run_half1_class001_unfil.mrc ]; then
      $BIN/relion_postprocess --i $P/$D/run_half1_class001_unfil.mrc \
        --o $ROOT/pp/$arm/refine_${SET}_s${seed} --mask MaskCreate/job020/mask.mrc \
        --angpix 1.244531 --mtf mtf_k2_200kV.star --mtf_angpix 0.885 \
        --auto_bfac --autob_lowres 10 > $ROOT/logs/pp_refine_${arm}_${SET}_s${seed}.log 2>&1
      echo "seed=$seed arm=$arm rc=$rc wall=$w iters=$(grep -c 'Expectation iteration' $ROOT/logs/refine_${arm}_${SET}_s${seed}.log) res=$(grep -m1 _rlnFinalResolution $ROOT/pp/$arm/refine_${SET}_s${seed}.star|awk '{print $2}') bfac=$(grep -m1 _rlnBfactorUsedForSharpening $ROOT/pp/$arm/refine_${SET}_s${seed}.star|awk '{print $2}') seed_used=$(grep -m1 _rlnRandomSeed $P/$D/run_optimiser.star|awk '{print $2}')"
    else
      echo "seed=$seed arm=$arm rc=$rc wall=$w NO HALF MAP"
    fi
  done
done
echo STAGE_C2_DONE
