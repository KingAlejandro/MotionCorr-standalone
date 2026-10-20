#!/bin/bash
# S1.3c-null SCARF census (one gpu-devel allocation; run with srun --overlap).
# Movies held only on SCARF: 10216-07..09, Falcon 3-04..09. Both grids. Arms:
# CPU (sweep's frozen-F build-F-cpu) and CUDA diag5: off / on (global+DW Hermitian
# projection) / null1 / null2 (size-matched random-sign row offsets, seeds 1 and 2).
set -u
export TMPDIR=/tmp
H=$HOME/mc-s13c; O=$H/results-n
W=/tmp/s13n-${SLURM_JOB_ID}
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export LD_LIBRARY_PATH=$CU/lib64:$HOME/nvcomp-sdk/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
CPUB=$HOME/mc-post-rc0-s1/build-F-cpu/motioncorr
GPUB=$H/build-diag5-cuda/motioncorr
SRC=$HOME/mc-post-rc0-s1/src-F
mkdir -p $W/data $W/inputs $W/runs $O
UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
{ hostname; echo "job $SLURM_JOB_ID uuid $UUID cpus $(taskset -cp $$)"; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader;
  sha256sum $CPUB $GPUB; df -h /tmp | tail -1; } > $O/host.txt
F3=EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification
declare -A REL=( [e10216-07]="EMPIAR-10216/data/FoilHole_14966017_Data_14966722_14966723_20180617_1418_Fractions.mrc"
  [e10216-08]="EMPIAR-10216/data/FoilHole_17063931_Data_14966722_14966723_20180617_1843_Fractions.mrc"
  [e10216-09]="EMPIAR-10216/data/FoilHole_17067881_Data_14966722_14966723_20180617_2252_Fractions.mrc"
  [e10474f3-04]="$F3/2019-06-21_20-32-04.700_eer_data_4096x4096.eer" [e10474f3-05]="$F3/2019-06-21_22-11-55.361_eer_data_4096x4096.eer"
  [e10474f3-06]="$F3/2019-06-21_23-43-39.840_eer_data_4096x4096.eer" [e10474f3-07]="$F3/2019-06-22_01-14-22.808_eer_data_4096x4096.eer"
  [e10474f3-08]="$F3/2019-06-22_02-45-31.984_eer_data_4096x4096.eer" [e10474f3-09]="$F3/2019-06-22_04-15-13.637_eer_data_4096x4096.eer" )
declare -A SHA=( [e10216-07]=aa00d15402e23e83e34bb8ab08654adf81f786522a8c1f40e7e34c9760b641b6
  [e10216-08]=64aa091288882a55e2faa9cb5cc20f124a98e7eeb862eff161d12d1f2837b413
  [e10216-09]=c342abbb3f3cd1b8ff8506c9b29b9e08cedf5e997da611a05708a9b2b1f259bf
  [e10474f3-04]=20f8a2968327c8fc4e1be64e5c9eda120e198d0ecc088f870890ec718f31c21b
  [e10474f3-05]=27bfe59b7e714cfa736a54b6f55d5d1cce6776a53e7706991e9bcdbe09ce1f73
  [e10474f3-06]=4e7eef3696bc58777f16dbe19eac4005498239d9f92a8cffa9d76d1b01f3bc3d
  [e10474f3-07]=f9db58e07b7df467e040594871d1ed4d1232fcfa363023dfb2afd84b2111a985
  [e10474f3-08]=d7e97c144c25904c4decb6b2c1b7098b0df3aa09227c20b2a8f43cab4cda5e44
  [e10474f3-09]=51a96ca3061b80ec1fb31383aa376f616c06d7eacc1bcc3b609a0be91ea0f012 )
common=(--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --i movies.star --j 8 --seed 1)
run() { id=$1 g=$2 arm=$3; shift 3
  l=$id-p$g-$arm; o=$W/runs/$l; mkdir -p $o
  fam=(--expected_frames 59); case $id in e10474f3*) fam=(--expected_frames 58 --eer_grouping 40 --eer_upsampling 1);; esac
  bin=$GPUB; gpu=(--gpu 0 --ingest auto); [ $arm = cpu ] && { bin=$CPUB; gpu=(); }
  args=("${common[@]}" --o $o/ --patch_x $g --patch_y $g "${fam[@]}" --ingest_witness $o/witness.txt "${gpu[@]}")
  ( cd $W/inputs/$id && env "$@" CUDA_VISIBLE_DEVICES=$( [ $arm = cpu ] && echo "" || echo $UUID ) \
      /usr/bin/time -v -o $o/time-v.log $bin "${args[@]}" > $o/stdout.log 2>&1 ); rc=$?
  printf '%s rc=%s bin=%s env=%s argv=%s\n' "$l" "$rc" "$bin" "$*" "${args[*]}" >> $O/runs.log
}
for id in e10216-07 e10216-08 e10216-09 e10474f3-04 e10474f3-05 e10474f3-06 e10474f3-07 e10474f3-08 e10474f3-09; do
  rel=${REL[$id]}; f=$W/data/$(basename $rel); ok=0
  for t in 1 2 3; do
    curl --fail --location --retry 4 --connect-timeout 30 -s -o $f.partial "https://ftp.ebi.ac.uk/empiar/world_availability/${rel#EMPIAR-}" && \
      [ "$(sha256sum < $f.partial | cut -c1-64)" = "${SHA[$id]}" ] && { mv $f.partial $f; ok=1; break; }
  done
  echo "download $id ok=$ok $(date -u +%FT%TZ)" >> $O/downloads.log
  [ $ok = 1 ] || continue
  link=$(sed -n 's#^Movies/\(.*\) 1$#\1#p' $H/inputs/$id.star)
  mkdir -p $W/inputs/$id/Movies; ln -sfn $f $W/inputs/$id/Movies/$link; cp $H/inputs/$id.star $W/inputs/$id/movies.star
  sha256sum $W/inputs/$id/movies.star >> $O/inputs.sha256
  for g in 5 3; do
    run $id $g cpu X=0
    run $id $g off X=0
    run $id $g on MC_DIAG_C2R_HERMITIAN_GLOBAL=1 MC_DIAG_C2R_HERMITIAN_DW=1
    run $id $g null1 MC_DIAG_NULL_ROWS=1
    run $id $g null2 MC_DIAG_NULL_ROWS=2
    for arm in off on null1 null2; do
      python3 $SRC/tools/compare_motioncorr.py --ref $W/runs/$id-p$g-cpu --test $W/runs/$id-p$g-$arm --gate backend \
        --json-out $W/runs/$id-p$g-$arm/backend.json > $W/runs/$id-p$g-$arm/backend.txt 2>&1
      echo "$id-p$g-$arm $(grep 'Relative RMSE' $W/runs/$id-p$g-$arm/backend.txt)" >> $O/relrmse.log
    done
  done
  rsync -a --exclude '*.mrc' --exclude '*.mrcs' --exclude '*.pdf' --exclude '*.eps' $W/runs/ $O/runs/
  rm -rf $W/runs/$id-* $f
done
rm -rf $W
echo SCARF-DONE >> $O/relrmse.log
