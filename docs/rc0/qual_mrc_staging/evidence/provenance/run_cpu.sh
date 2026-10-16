#!/bin/bash
export TMPDIR=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth
PY=/home/alex/mc-env/bin/python3
S=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/src/docs/rc0/qual_mrc_staging
for b in 1db86902 4b849165; do
  export MC_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/build/cpu-$b/motioncorr
  $PY -I $S/synth_mrc_matrix.py --cpu --binary /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/cpurun.sh --work /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth/cpu-$b --out /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth/cpu-$b.json --section matrix --keep-outputs > /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/cpu-matrix-$b.log 2>&1
done
for b in 1db86902 4b849165; do
  export MC_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/build/cpu-$b/motioncorr
  $PY -I $S/real_data_identity.py --cpu --binary /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/cpurun.sh --inputs /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/inputs --work /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/runs/cpu-$b --out /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/runs/cpu-$b.json --families e10216,e10164 --configs G >> /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/cpu-real.log 2>&1
done
echo ALLDONE >> /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/cpu-real.log
