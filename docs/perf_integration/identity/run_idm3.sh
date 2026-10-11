#!/bin/bash
# Identity matrix: main (9d14275) vs RC, 4 movies. Output: idm/out/<cfg>/<arm>, rc in idm/rc.txt
set -u
I=/home/alex/mc-rc/idm; cd $I/data
MAIN=/home/alex/mc-prof-abc/build-main/motioncorr
RC=/home/alex/mc-rc/build-rc/motioncorr
BASE="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8"
GPU="--gpu 0 --ingest auto"
run() { # cfg arm bin env args...
  local cfg=$1 arm=$2 bin=$3 envs=$4; shift 4
  local o=$I/out/$cfg/$arm; rm -rf $o; mkdir -p $o
  env $envs CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 taskset -c 96-103 $bin --i four.star --o $o/ $BASE "$@" > $o.stdout 2>&1
  echo "$cfg $arm rc=$?" >> $I/rc.txt
}
echo PHASE3 >> $I/rc.txt
for arm in main rc; do
  b=$MAIN; [ $arm = rc ] && b=$RC
  run bin2      $arm $b "" $GPU --bin_factor 1.25 --even_odd_split --save_noDW
  run bin2late  $arm $b "" $GPU --bin_factor 1.25 --no_early_binning --even_odd_split --save_noDW
done
run bin2     rc_poison $RC MOTIONCORR_FRAME_POOL_POISON=1 $GPU --bin_factor 1.25 --even_odd_split --save_noDW
run bin2late rc_poison $RC MOTIONCORR_FRAME_POOL_POISON=1 $GPU --bin_factor 1.25 --no_early_binning --even_odd_split --save_noDW
for c in bin2 bin2late; do for a in rc rc_poison; do echo "== $c $a"; python3 $I/cmp_trees.py $I/out/$c/main $I/out/$c/$a; done; done > $I/cmp3.txt 2>&1
echo ALLDONE3 >> $I/rc.txt
