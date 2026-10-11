#!/bin/bash
# Identity matrix, main 1a99da0 vs perf/vram-tier1, on 4GPUs GPU1.
# default and *_dw configurations are the ones where dose weighting consumes the
# real-space movie; eo/eo_nodw/bin_late keep it. Rule: docs/perf_integration/identity/cmp_trees.py.
set -u
W=/home/alex/mc-vram1-idm; rm -rf $W; mkdir -p $W/out
L=$W/idm.log; : > $L
MAIN=/home/alex/mc-vram1-main/build/motioncorr; CAND=/home/alex/mc-vram1/build/motioncorr
CMP=/home/alex/mc-vram1/docs/perf_integration/identity/cmp_trees.py
echo "main $(git -C /home/alex/mc-vram1-main rev-parse --short HEAD) cand $(git -C /home/alex/mc-vram1 rev-parse --short HEAD)" >> $L
BASE="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --j 8"
run() { # dir star cfg arm bin env args...
  local dir=$1 star=$2 cfg=$3 arm=$4 bin=$5 envs=$6; shift 6
  local o=$W/out/$cfg/$arm; mkdir -p $o
  ( cd $dir && flock /tmp/motioncorr-gpu1-correctness.lock env $envs CUDA_VISIBLE_DEVICES=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d taskset -c 64-71 $bin --i $star --o $o/ $BASE "$@" > $o.stdout 2>&1 )
  echo "$cfg $arm rc=$?" >> $L
}
D=/home/alex/mc-rc/idm/data; M=/home/alex/mc-rc/mixed; G="--gainref Movies/gain.mrc"
for arm in main cand; do b=$MAIN; [ $arm = cand ] && b=$CAND
  run $D four.star default     $arm $b "" $G --gpu 0 --ingest nvcomp
  run $D four.star eo          $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split
  run $D four.star eo_nodw     $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $D four.star bin_late    $arm $b "" $G --gpu 0 --ingest auto --bin_factor 1.25 --no_early_binning --even_odd_split --save_noDW
  run $D four.star bin_late_dw $arm $b "" $G --gpu 0 --ingest auto --bin_factor 1.25 --no_early_binning
  run $D four.star cpu         $arm $b "" $G --even_odd_split --save_noDW
  run $M mixed_xy.star mixed    $arm $b "" --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $M mixed_xy.star mixed_dw $arm $b "" --gpu 0 --ingest nvcomp
done
P=MOTIONCORR_FRAME_POOL_POISON=1
run $D four.star default  cand_poison $CAND $P $G --gpu 0 --ingest nvcomp
run $D four.star eo_nodw  cand_poison $CAND $P $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
run $M mixed_xy.star mixed_dw cand_poison $CAND $P --gpu 0 --ingest nvcomp
for c in default eo eo_nodw bin_late bin_late_dw cpu mixed mixed_dw; do
  echo "== $c cand: $(python3 $CMP $W/out/$c/main $W/out/$c/cand | head -3 | tr '\n' ' ')" >> $L; done
for c in default eo_nodw mixed_dw; do
  echo "== $c cand_poison: $(python3 $CMP $W/out/$c/main $W/out/$c/cand_poison | head -3 | tr '\n' ' ')" >> $L; done
# Comparator controls: must report DIFFERENT.
echo "== control inventory (main eo vs main eo_nodw): $(python3 $CMP $W/out/eo/main $W/out/eo_nodw/main | head -1)" >> $L
cp -r $W/out/default/main $W/out/default/flip
f=$(find $W/out/default/flip -name '*.mrc' | sort | head -1)
python3 - "$f" <<'PY'
import sys; p = sys.argv[1]; b = bytearray(open(p, 'rb').read()); b[4096] ^= 1; open(p, 'wb').write(b)
PY
echo "== control payload bit flip (main default vs flipped copy): $(python3 $CMP $W/out/default/main $W/out/default/flip | head -1)" >> $L
grep -h "Dose-weighting scratch borrowed" $W/out/default/cand/Movies/*.log | sort | uniq -c >> $L
echo "borrow lines in cand eo_nodw logs: $(cat $W/out/eo_nodw/cand/Movies/*.log | grep -c 'Dose-weighting scratch borrowed')" >> $L
echo IDM-DONE >> $L
