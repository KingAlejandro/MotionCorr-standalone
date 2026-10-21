#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-peakfit
W=$S/extra
mkdir -p $W/data $W/inputs $W/stars $W/sweep/runs
tar -xf $S/mc-extra-stars.tar -C $W/stars
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
 rel=${REL[$id]}; f=$W/data/$(basename $rel)
 if [ ! -f "$f" ] || ! echo "${SHA[$id]}  $f" | sha256sum -c - >/dev/null; then
  curl --fail --location --retry 4 --connect-timeout 30 -s -o $f.partial "https://ftp.ebi.ac.uk/empiar/world_availability/${rel#EMPIAR-}"
  echo "${SHA[$id]}  $f.partial" | sha256sum -c - >> $S/logs/extra-downloads.log
  mv $f.partial $f
 fi
 link=$(sed -n 's#^Movies/\(.*\) 1$#\1#p' $W/stars/$id.star)
 mkdir -p $W/inputs/$id/Movies $W/sweep/runs/$id-p5-F-cuda
 ln -sfn $f $W/inputs/$id/Movies/$link
 cp $W/stars/$id.star $W/inputs/$id/movies.star
 python3 - "$W" "$id" <<'PYJSON'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]); id=sys.argv[2]
a=['/unused/motioncorr','--use_own','--dose_weighting','--dose_per_frame','1.0','--bfactor','150','--i','movies.star','--o','/unused/','--j','8','--seed','1','--patch_x','5','--patch_y','5','--expected_frames','59','--ingest_witness','/unused','--gpu','0','--ingest','auto']
if id.startswith('e10474f3'):a[a.index('59')]='58';a+=['--eer_grouping','40','--eer_upsampling','1']
json.dump({'argv':a,'cwd':str(w/'inputs'/id)},open(w/'sweep/runs'/('%s-p5-F-cuda'%id)/'run.json','w'))
PYJSON
 export S13C_ROOT=$S S13C_SWEEP=$W/sweep LANE_GPU=2
 for arm in cpu A0 A1; do
  args=(--gpu); bin=$S/build-A1/motioncorr; sha=9a834380
  if [ "$arm" != A1 ]; then bin=$S/build-A0/motioncorr;sha=4837b210;fi
  if [ "$arm" = cpu ]; then args=();fi
  MC_SOURCE_SHA=$sha /usr/bin/python3 $S/tools/run_c.py --sweep-label $id-p5-F-cuda --label $id-G-$arm --binary $bin --config G --save-nodw "${args[@]}" --env 'MC_DIAG_CCF={out}/ccf.txt' --env 'MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt' >> $S/logs/extra-global-campaign.log 2>&1
 done
done
echo DONE >> $S/logs/extra-global-campaign.log
