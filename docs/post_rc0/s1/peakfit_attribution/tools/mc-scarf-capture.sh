#!/bin/bash
set -eu
H=$HOME/mc-peakfit; W=/tmp/peakfit-capture2-$SLURM_JOB_ID; O=$W/results; R=$H/captures-final
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export TMPDIR=/tmp OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=""
export LD_LIBRARY_PATH=$CU/lib64:$HOME/nvcomp-sdk/lib
mkdir -p $O/runs $W/data $W/inputs $R
trap 'rsync -a "$O/" "$R/"' EXIT
# Reuse this task's completed payload from its interrupted capture.
for live in /tmp/peakfit-capture-$SLURM_JOB_ID/data/* /tmp/peakfit-$SLURM_JOB_ID/data/*; do
 [ -f "$live" ] || continue
 case $live in *.partial) continue;; esac
 ln "$live" "$W/data/$(basename "$live")" 2>/dev/null || true
done
{ date -u; hostname; taskset -cp $$; echo job=$SLURM_JOB_ID; } > $O/host.txt
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

for id in e10216-07 e10216-08 e10216-09 e10474f3-04 e10474f3-05 e10474f3-06 e10474f3-07 e10474f3-08 e10474f3-09; do
 rel=${REL[$id]}; f=$W/data/$(basename $rel); live=/tmp/peakfit-$SLURM_JOB_ID/data/$(basename $rel)
 if [ -f "$f" ]; then ln "$f" "$f.partial"; elif [ -f $live ]; then cp --reflink=auto "$live" "$f.partial" || true; fi
 if [ ! -f "$f.partial" ] || ! echo "${SHA[$id]}  $f.partial" | sha256sum -c - > /dev/null; then
  curl --fail --location --retry 4 --connect-timeout 30 -s -o "$f.partial" "https://ftp.ebi.ac.uk/empiar/world_availability/${rel#EMPIAR-}"
 fi
 echo "${SHA[$id]}  $f.partial" | sha256sum -c - >> $O/downloads.log
 mv $f.partial $f
 link=$(sed -n 's#^Movies/\(.*\) 1$#\1#p' $HOME/mc-s13c/inputs/$id.star)
 mkdir -p $W/inputs/$id/Movies
 ln -s "$f" "$W/inputs/$id/Movies/$link"
 cp $HOME/mc-s13c/inputs/$id.star $W/inputs/$id/movies.star
 fam=(--expected_frames 59);case $id in e10474f3*) fam=(--expected_frames 58 --eer_grouping 40 --eer_upsampling 1);; esac
 for g in 5 3; do
  out=$O/runs/$id-p$g-cpu;mkdir -p $out
  set +e
  (cd $W/inputs/$id && env MC_DIAG_CCF=$out/ccf.txt MC_DIAG_GLOBAL_SHIFTS_OUT=$out/global.txt /usr/bin/time -v -o $out/time-v.log $H/build-A0/motioncorr --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --i movies.star --o $out/ --j 8 --patch_x $g --patch_y $g "${fam[@]}" > $out/stdout.log 2>&1)
  rc=$?;echo "$id-p$g rc=$rc source=4837b210 bin=$H/build-A0/motioncorr" >> $O/runs.log
  set -e
  [ $rc = 0 ] || exit $rc
  ref=$H/results/runs/$id-p$g-cpu
  for t in $(seq 1 120); do [ -f "$ref/retained-stdout.log" ] && break;sleep 5;done
  python3 $H/identity.py "$ref" "$out" > $out/identity-reference.json
 done
 rm -f "$f"
 echo "$id DONE $(date -u +%FT%TZ)" >> $O/progress.txt
 rsync -a "$O/" "$R/"
done
echo DONE >> $O/progress.txt
