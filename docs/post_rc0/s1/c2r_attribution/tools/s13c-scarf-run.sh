#!/bin/bash
# S1.3c SCARF campaign (one gpu-devel allocation; run with srun --overlap).
# SCARF-only #243 screen-positive 4096^2 movies, both grids: CPU (sweep's frozen-F
# build-F-cpu) and CUDA diag4 off / global C2R projection / global+DW projection.
set -u
export TMPDIR=/tmp
H=$HOME/mc-s13c
W=/tmp/s13c-${SLURM_JOB_ID}
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export LD_LIBRARY_PATH=$CU/lib64:$HOME/nvcomp-sdk/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
CPUB=$HOME/mc-post-rc0-s1/build-F-cpu/motioncorr
GPUB=$H/build-diag4-cuda/motioncorr
SRC=$HOME/mc-post-rc0-s1/src-F
mkdir -p $W/data $W/inputs $W/runs $H/results
UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
{ hostname; echo "job $SLURM_JOB_ID uuid $UUID cpus $(taskset -cp $$)"; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader;
  sha256sum $CPUB $GPUB; } > $H/results/host.txt
declare -A REL=( [e10216-07]="EMPIAR-10216/data/FoilHole_14966017_Data_14966722_14966723_20180617_1418_Fractions.mrc"
                 [e10216-08]="EMPIAR-10216/data/FoilHole_17063931_Data_14966722_14966723_20180617_1843_Fractions.mrc"
                 [e10216-09]="EMPIAR-10216/data/FoilHole_17067881_Data_14966722_14966723_20180617_2252_Fractions.mrc"
                 [e10474f3-04]="EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-32-04.700_eer_data_4096x4096.eer" )
declare -A SHA=( [e10216-07]=aa00d15402e23e83e34bb8ab08654adf81f786522a8c1f40e7e34c9760b641b6
                 [e10216-08]=64aa091288882a55e2faa9cb5cc20f124a98e7eeb862eff161d12d1f2837b413
                 [e10216-09]=c342abbb3f3cd1b8ff8506c9b29b9e08cedf5e997da611a05708a9b2b1f259bf
                 [e10474f3-04]=20f8a2968327c8fc4e1be64e5c9eda120e198d0ecc088f870890ec718f31c21b )
declare -A LINK=( [e10216-07]=FoilHole_14966017_Data_14966722_14966723_20180617_1418_Fractions.mrcs
                  [e10216-08]=FoilHole_17063931_Data_14966722_14966723_20180617_1843_Fractions.mrcs
                  [e10216-09]=FoilHole_17067881_Data_14966722_14966723_20180617_2252_Fractions.mrcs
                  [e10474f3-04]=2019-06-21_20-32-04_700_eer_data_4096x4096.eer )
for id in e10216-07 e10216-08 e10216-09 e10474f3-04; do
  rel=${REL[$id]}; f=$W/data/$(basename $rel)
  ok=0
  for t in 1 2 3; do
    curl --fail --location --retry 4 --connect-timeout 30 -s -o $f.partial "https://ftp.ebi.ac.uk/empiar/world_availability/${rel#EMPIAR-}" && \
      [ "$(sha256sum < $f.partial | cut -c1-64)" = "${SHA[$id]}" ] && { mv $f.partial $f; ok=1; break; }
  done
  echo "download $id ok=$ok $(date -u +%FT%TZ)" >> $H/results/downloads.log
  [ $ok = 1 ] || continue
  mkdir -p $W/inputs/$id/Movies; ln -sfn $f $W/inputs/$id/Movies/${LINK[$id]}; cp $H/inputs/$id.star $W/inputs/$id/movies.star
  sha256sum $W/inputs/$id/movies.star >> $H/results/inputs.sha256
done
common=(--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --i movies.star --j 8 --seed 1)
run() { id=$1 g=$2 arm=$3; shift 3
  l=$id-p$g-$arm; o=$W/runs/$l; mkdir -p $o
  fam=(--expected_frames 59); case $id in e10474f3*) fam=(--expected_frames 58 --eer_grouping 40 --eer_upsampling 1);; esac
  bin=$GPUB; gpu=(--gpu 0 --ingest auto); [ $arm = cpu ] && { bin=$CPUB; gpu=(); }
  args=("${common[@]}" --o $o/ --patch_x $g --patch_y $g "${fam[@]}" --ingest_witness $o/witness.txt "${gpu[@]}")
  ( cd $W/inputs/$id && env "$@" CUDA_VISIBLE_DEVICES=$( [ $arm = cpu ] && echo "" || echo $UUID ) \
      /usr/bin/time -v -o $o/time-v.log $bin "${args[@]}" > $o/stdout.log 2>&1 ); rc=$?
  printf '%s rc=%s bin=%s env=%s argv=%s\n' "$l" "$rc" "$bin" "$*" "${args[*]}" >> $H/results/runs.log
}
for id in e10216-07 e10216-08 e10216-09 e10474f3-04; do
  [ -d $W/inputs/$id ] || continue
  for g in 5 3; do
    run $id $g cpu X=0
    run $id $g off X=0
    run $id $g glob MC_DIAG_C2R_HERMITIAN_GLOBAL=1
    run $id $g globdw MC_DIAG_C2R_HERMITIAN_GLOBAL=1 MC_DIAG_C2R_HERMITIAN_DW=1
    for arm in off glob globdw; do
      python3 $SRC/tools/compare_motioncorr.py --ref $W/runs/$id-p$g-cpu --test $W/runs/$id-p$g-$arm --gate backend \
        --json-out $W/runs/$id-p$g-$arm/backend.json > $W/runs/$id-p$g-$arm/backend.txt 2>&1
      echo "$id-p$g-$arm $(grep 'Relative RMSE' $W/runs/$id-p$g-$arm/backend.txt)" >> $H/results/relrmse.log
    done
    for arm in glob globdw; do
      cmp -s $W/runs/$id-p$g-off/Movies/*.star $W/runs/$id-p$g-$arm/Movies/*.star; echo "$id-p$g-$arm star_identical_to_off rc=$?" >> $H/results/relrmse.log
    done
  done
done
# Keep everything except MRC/PDF/EPS products and the movies.
rsync -a --exclude '*.mrc' --exclude '*.mrcs' --exclude '*.pdf' --exclude '*.eps' $W/runs/ $H/results/runs/
rm -rf $W
echo SCARF-DONE >> $H/results/relrmse.log
