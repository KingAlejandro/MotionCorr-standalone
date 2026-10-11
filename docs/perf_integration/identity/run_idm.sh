#!/bin/bash
# Identity matrix: main (9d14275) vs RC, 4 movies. Output: idm/out/<cfg>/<arm>, rc in idm/rc.txt
set -u
I=/home/alex/mc-rc/idm; cd $I/data
MAIN=/home/alex/mc-prof-abc/build-main/motioncorr
RC=/home/alex/mc-rc/build-rc/motioncorr
BASE="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8"
GPU="--gpu 0 --ingest nvcomp"
run() { # cfg arm bin env args...
  local cfg=$1 arm=$2 bin=$3 envs=$4; shift 4
  local o=$I/out/$cfg/$arm; rm -rf $o; mkdir -p $o
  env $envs CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 taskset -c 96-103 $bin --i four.star --o $o/ $BASE "$@" > $o.stdout 2>&1
  echo "$cfg $arm rc=$?" >> $I/rc.txt
}
: > $I/rc.txt
for arm in main rc; do
  b=$MAIN; [ $arm = rc ] && b=$RC
  run eo        $arm $b "" $GPU --even_odd_split
  run eo_nodw   $arm $b "" $GPU --even_odd_split --save_noDW
  run bin2      $arm $b "" $GPU --bin_factor 2 --even_odd_split --save_noDW
  run bin2late  $arm $b "" $GPU --bin_factor 2 --no_early_binning --even_odd_split --save_noDW
  run cpu       $arm $b "" --even_odd_split --save_noDW
done
run eo_nodw  rc_poison $RC MOTIONCORR_FRAME_POOL_POISON=1 $GPU --even_odd_split --save_noDW
run bin2late rc_poison $RC MOTIONCORR_FRAME_POOL_POISON=1 $GPU --bin_factor 2 --no_early_binning --even_odd_split --save_noDW
run cpu      rc_poison $RC MOTIONCORR_FRAME_POOL_POISON=1 --even_odd_split --save_noDW
run eo_nodw  rc_nopool $RC MOTIONCORR_FRAME_POOL=0 $GPU --even_odd_split --save_noDW
for c in eo eo_nodw bin2 bin2late cpu; do echo "== $c rc";  python3 $I/cmp_trees.py $I/out/$c/main $I/out/$c/rc; done > $I/cmp.txt 2>&1
for c in eo_nodw bin2late cpu; do echo "== $c rc_poison"; python3 $I/cmp_trees.py $I/out/$c/main $I/out/$c/rc_poison; done >> $I/cmp.txt 2>&1
echo "== eo_nodw rc_nopool" >> $I/cmp.txt; python3 $I/cmp_trees.py $I/out/eo_nodw/main $I/out/eo_nodw/rc_nopool >> $I/cmp.txt 2>&1
echo ALLDONE >> $I/rc.txt
