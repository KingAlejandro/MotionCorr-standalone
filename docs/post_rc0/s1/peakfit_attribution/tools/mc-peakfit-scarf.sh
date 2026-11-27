#!/bin/bash
set -eu
export TMPDIR=/tmp OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
H=$HOME/mc-peakfit
O=$H/results
W=/tmp/peakfit-${SLURM_JOB_ID}
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH=$CU/bin:$PATH
export LD_LIBRARY_PATH=$CU/lib64:$HOME/nvcomp-sdk/lib
mkdir -p $H/logs $O $W/data $W/inputs $W/runs
{ hostname; date -u; echo job=$SLURM_JOB_ID; taskset -cp $$; nvidia-smi -L; df -h /tmp; } > $O/host.txt
for arm in A0 A1; do
 mkdir -p $H/src-$arm
 tar -xf $HOME/mc-s13c/mc-diag-$arm.tar -C $H/src-$arm
 set +e
 cmake -S $H/src-$arm -B $H/build-$arm -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=$CU/bin/nvcc -DCUDAToolkit_ROOT=$CU -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$HOME/nvcomp-sdk > $H/logs/configure-$arm.log 2>&1
 rc=$?; echo $rc > $H/logs/configure-$arm.exit; [ $rc = 0 ] || exit $rc
 cmake --build $H/build-$arm -j8 --target motioncorr > $H/logs/build-$arm.log 2>&1
 rc=$?; echo $rc > $H/logs/build-$arm.exit; [ $rc = 0 ] || exit $rc
 set -e
 sha256sum $H/build-$arm/motioncorr >> $O/binaries.sha256
done
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

CPUB=$HOME/mc-post-rc0-s1/build-F-cpu/motioncorr
PRB=$HOME/mc-s13c/build-pr254-cuda/motioncorr
UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
common=(--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --i movies.star --j 8 --seed 1)
run() {
 local id=$1 g=$2 arm=$3; shift 3
 local l=$id-p$g-$arm o=$W/runs/$id-p$g-$arm
 mkdir -p $o
 local bin=$H/build-A1/motioncorr sha=9a834380
 local -a gpu=(--gpu 0 --ingest auto) fam=(--expected_frames 59) extra=()
 case $id in e10474f3*) fam=(--expected_frames 58 --eer_grouping 40 --eer_upsampling 1);; esac
 case $arm in
  cpu) bin=$CPUB; sha=6d68e2d6; gpu=();;
  A0) bin=$H/build-A0/motioncorr; sha=4837b210;;
  A2) extra+=(MC_DIAG_ZERO_CCF_DC=1);;
  N1|N2) bin=$H/build-A0/motioncorr; sha=4837b210; extra+=(MC_DIAG_FIT_NULL=${arm:1} MC_DIAG_NULL_RECORD=$o/null-dose.txt);;
  parent) bin=$PRB; sha=8b55d5da;;
 esac
 local -a args=("${common[@]}" --o $o/ --patch_x $g --patch_y $g "${fam[@]}" --ingest_witness $o/witness.txt "${gpu[@]}")
 # srun inherits the eight allocated CPUs, CUDA_VISIBLE_DEVICES uses UUID.
 set +e
 (cd $W/inputs/$id && env "${extra[@]}" MC_DIAG_CCF=$o/ccf.txt MC_DIAG_GLOBAL_SHIFTS_OUT=$o/global.txt CUDA_VISIBLE_DEVICES=$( [ $arm = cpu ] && echo "" || echo $UUID ) /usr/bin/time -v -o $o/time-v.log $bin "${args[@]}" > $o/stdout.log 2>&1) &
 local pid=$!
 python3 $H/witness.py $pid $o/gpu-witness.txt & local wit=$!
 wait $pid; local rc=$?; wait $wit
 set -e
 printf '%s rc=%s sha=%s bin=%s env=%s argv=%s\n' "$l" "$rc" "$sha" "$bin" "${extra[*]}" "${args[*]}" >> $O/runs.log
 [ $rc = 0 ] || return $rc
 cp $o/stdout.log $o/retained-stdout.log
}
for id in e10216-07 e10216-08 e10216-09 e10474f3-04 e10474f3-05 e10474f3-06 e10474f3-07 e10474f3-08 e10474f3-09; do
 rel=${REL[$id]}; f=$W/data/$(basename $rel)
 curl --fail --location --retry 4 --connect-timeout 30 -s -o $f.partial "https://ftp.ebi.ac.uk/empiar/world_availability/${rel#EMPIAR-}"
 echo "${SHA[$id]}  $f.partial" | sha256sum -c - >> $O/downloads.log
 mv $f.partial $f
 link=$(sed -n 's#^Movies/\(.*\) 1$#\1#p' $HOME/mc-s13c/inputs/$id.star)
 mkdir -p $W/inputs/$id/Movies
 ln -s $f $W/inputs/$id/Movies/$link
 cp $HOME/mc-s13c/inputs/$id.star $W/inputs/$id/movies.star
 sha256sum $f $W/inputs/$id/movies.star >> $O/inputs.sha256
 for g in 5 3; do
  for arm in cpu parent A0 A1 A2 N1 N2; do run $id $g $arm; done
  for arm in parent A0 A1 A2 N1 N2; do
   set +e
   python3 $H/src-A0/tools/compare_motioncorr.py --ref $W/runs/$id-p$g-cpu --test $W/runs/$id-p$g-$arm --gate backend --json-out $W/runs/$id-p$g-$arm/backend.json > $W/runs/$id-p$g-$arm/backend.txt 2>&1
   rc=$?
   set -e
   echo "$id-p$g-$arm comparator_rc=$rc $(grep 'Relative RMSE' $W/runs/$id-p$g-$arm/backend.txt)" >> $O/relrmse.log
  done
 done
 # Retain images for the new experiment and any required follow-up controls.
 rsync -a --exclude '*.pdf' --exclude '*.eps' $W/runs/ $O/runs/
 # Only remove this task's scratch movie, not products or existing references.
 rm -f $f
 echo "$id DONE $(date -u +%FT%TZ)" >> $O/progress.txt
done
echo DONE >> $O/progress.txt
