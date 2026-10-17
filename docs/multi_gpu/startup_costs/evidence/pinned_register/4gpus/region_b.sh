#!/bin/bash
# Region B (bench lock held): identity matrix, main 116eb04a vs step 2 alone. GPU0 lock per run.
set -u
S=/dev/shm/mcs2; MAIN=$S/b-t-main/motioncorr; CAND=$S/b-t-s2/motioncorr
CMP=$S/src-s2/docs/perf_integration/identity/cmp_trees.py
BASE="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --j 8"
I=$S/idm; rm -rf $I; mkdir -p $I; L=$I/summary.txt; : > $L
echo "region B start $(date -Is)"
echo "main sha=$(sha256sum $MAIN | cut -c1-16) cand sha=$(sha256sum $CAND | cut -c1-16) cmp sha=$(sha256sum $CMP | cut -c1-16) $(date -Is)" >> $L
run() { # dir star cfg arm bin env args...
  local dir=$1 star=$2 cfg=$3 arm=$4 bin=$5 envs=$6; shift 6
  local o=$I/out/$cfg/$arm; rm -rf $o; mkdir -p $o
  ( cd $dir && flock -w 28800 /tmp/motioncorr-gpu0-correctness.lock env $envs CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c 96-103 $bin --i $star --o $o/ $BASE "$@" > $o.stdout 2>&1 )
  echo "$cfg $arm rc=$?" >> $L
}
D=/home/alex/mc-rc/idm/data; M=/home/alex/mc-rc/mixed; G="--gainref Movies/gain.mrc"
P=MOTIONCORR_FRAME_POOL_POISON=1
for arm in main cand; do b=$MAIN; [ $arm = cand ] && b=$CAND
  run $D four.star eo       $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split
  run $D four.star eo_nodw  $arm $b "" $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $D four.star bin_late $arm $b "" $G --gpu 0 --ingest auto --bin_factor 1.25 --no_early_binning --even_odd_split --save_noDW
  run $D four.star cpu      $arm $b "" $G --even_odd_split --save_noDW
  run $M mixed_xy.star mixed     $arm $b "" --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
  run $M mixed_xy.star mixed_cpu $arm $b "" --even_odd_split --save_noDW
done
run $D four.star eo_nodw_poison main $MAIN $P $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
run $D four.star eo_nodw_poison cand $CAND $P $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
run $D four.star eo_nodw cand_nopinreg $CAND MOTIONCORR_PINNED_REGISTER=0 $G --gpu 0 --ingest nvcomp --even_odd_split --save_noDW
# the candidate takes the registered path (and the fallback switch reaches cudaHostAlloc)
echo "== log lines: cand eo_nodw: $(grep -rh 'pinned staging pool\|hugepage registration' $I/out/eo_nodw/cand --include='*.log' | sort | uniq -c | head -3 | tr '\n' ' ')" >> $L
for c in eo eo_nodw bin_late cpu mixed mixed_cpu eo_nodw_poison; do echo "== $c main-vs-cand: $(python3 $CMP $I/out/$c/main $I/out/$c/cand | head -3 | tr '\n' ' ')" >> $L; done
echo "== eo_nodw main-vs-cand_nopinreg: $(python3 $CMP $I/out/eo_nodw/main $I/out/eo_nodw/cand_nopinreg | head -3 | tr '\n' ' ')" >> $L
echo "== control A (main eo vs main eo_nodw, must differ): $(python3 $CMP $I/out/eo/main $I/out/eo_nodw/main | head -1)" >> $L
cp -r $I/out/eo_nodw/cand $I/ctl_flip; f=$(find $I/ctl_flip -name "*.mrc" | sort | head -1)
python3 - "$f" <<'PYEOF'
import sys
p = sys.argv[1]; b = bytearray(open(p, "rb").read()); b[-1000] ^= 1; open(p, "wb").write(b)
PYEOF
echo "== control B (cand eo_nodw with one payload byte flipped vs main, must differ): $(python3 $CMP $I/out/eo_nodw/main $I/ctl_flip | head -2 | tr '\n' ' ')" >> $L
echo IDM-DONE >> $L
rm -rf $I/out $I/ctl_flip
echo "region B end $(date -Is)"
