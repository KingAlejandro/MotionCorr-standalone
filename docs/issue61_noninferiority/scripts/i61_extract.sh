#!/bin/bash
# Issue 61 Stage B1: matched re-extraction. Identical command in every arm.
set -u
ROOT=/home/alex/mc-issue61
BIN=/home/alex/relion-container-tests/bin/relion-container-bin-r2
for arm in $ARMS; do
  P=$ROOT/proj/$arm; cd "$P" || exit 1
  rm -rf Extract61; mkdir -p Extract61
  /usr/bin/time -v $BIN/relion_preprocess \
    --i CtfFind/job003/micrographs_ctf.star \
    --reextract_data_star Refine3D/job019/run_data.star \
    --recenter --recenter_x 0 --recenter_y 0 --recenter_z 0 \
    --part_star Extract61/particles.star --pick_star Extract61/extractpick.star \
    --part_dir Extract61/ --extract --extract_size 360 --minimum_pick_fom -3 \
    --scale 256 --norm --bg_radius 71 --white_dust -1 --black_dust -1 --invert_contrast \
    > $ROOT/logs/extract_$arm.log 2> $ROOT/logs/extract_$arm.time
  rc=$?
  echo "$arm rc=$rc $(grep -m1 'Elapsed (wall clock)' $ROOT/logs/extract_$arm.time|awk '{print $NF}') parts=$(grep -c 'mrcs' Extract61/particles.star 2>/dev/null)"
done
echo EXTRACT_DONE
