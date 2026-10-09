#!/bin/bash
# Default-policy identity: base 7d64043 vs this branch, 4 movies, 4GPUs GPU3.
# Output: $I/out/<cfg>/<arm>; results in $L.
set -u
W=/home/alex/mc-fft; I=$W/idm; L=$I/identity.txt
mkdir -p $I; : > $L
BASE_GPU=$W/build-base/motioncorr; BR_GPU=$W/build/motioncorr
BASE_CPU=$W/build-base-cpu/motioncorr; BR_CPU=$W/build-cpu/motioncorr
OPTS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --j 8"
GPU3=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
D=/home/alex/mc-rc/idm/data; M=/home/alex/mc-rc/mixed; G="--gainref Movies/gain.mrc"
run() { # dir star cfg arm bin env args...
  local dir=$1 star=$2 cfg=$3 arm=$4 bin=$5 envs=$6; shift 6
  local o=$I/out/$cfg/$arm; rm -rf $o; mkdir -p $o
  ( cd $dir && flock /tmp/motioncorr-gpu3-correctness.lock env $envs CUDA_VISIBLE_DEVICES=$GPU3 taskset -c 80-87 $bin --i $star --o $o/ $OPTS "$@" > $o.stdout 2>&1 )
  echo "$cfg $arm rc=$?" >> $L
}
for arm in base br; do
  if [ $arm = base ]; then b=$BASE_GPU; c=$BASE_CPU; else b=$BR_GPU; c=$BR_CPU; fi
  run $D four.star eo       $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split
  run $D four.star eo_nodw  $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $D four.star bin_late $arm $b "" $G --gpu 0 --ingest auto --bin_factor 1.25 --no_early_binning --even_odd_split --save_noDW
  run $D four.star ps       $arm $b "" $G --gpu 0 --ingest nvcomp --grouping_for_ps 4
  run $D four.star cpu      $arm $b "" $G --even_odd_split --save_noDW
  run $D four.star cpu_only $arm $c "" $G --even_odd_split --save_noDW
  run $M mixed_xy.star mixed     $arm $b "" --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $M mixed_xy.star mixed_cpu $arm $b "" --even_odd_split --save_noDW
done
run $D four.star eo_nodw br_poison $BR_GPU MOTIONCORR_FRAME_POOL_POISON=1 $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
run $D four.star eo_nodw br_exact  $BR_GPU "" $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW --fft_size_policy exact
run $D four.star eo_nodw br_fast   $BR_GPU "" $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW --fft_size_policy fast
run $D four.star ps      br_fast   $BR_GPU "" $G --gpu 0 --ingest nvcomp --grouping_for_ps 4 --fft_size_policy fast
run $M mixed_xy.star mixed br_poison $BR_GPU MOTIONCORR_FRAME_POOL_POISON=1 --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
cmp() { echo "== $1 $3: $(python3 $W/src/docs/fft_size_policy/scripts/cmp_trees.py $I/out/$1/$2 $I/out/$1/$3 | head -3 | tr "\n" " ")" >> $L; }
for c in eo eo_nodw bin_late ps cpu cpu_only mixed mixed_cpu; do cmp $c base br; done
cmp eo_nodw base br_poison; cmp eo_nodw base br_exact; cmp mixed base br_poison
# fast with --grouping_for_ps falls back to exact sizes, so it must be identical too.
cmp ps base br_fast
# Controls, must differ: the comparator sees a noDW change and the fast policy.
cmp eo_nodw base br_fast
echo "== control eo vs eo_nodw (base): $(python3 $W/src/docs/fft_size_policy/scripts/cmp_trees.py $I/out/eo/base $I/out/eo_nodw/base | head -1)" >> $L
grep -h "fft_size_policy" $I/out/ps/br_fast/*/*.log 2>/dev/null | sort | uniq -c >> $L
echo IDENTITY-DONE >> $L
