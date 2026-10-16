#!/bin/bash
# Two workers sharing GPU0 vs one worker, same binary (current main 9d14275 = build-main2).
# Fixed CPU budget: 8 CPUs total (96-103). One worker: --j 8 on 96-103.
# Two workers: --j 4 each on 96-99 / 100-103. Also a 16-CPU two-worker arm (--j 8 each, 96-103 + 104-111).
W=/home/alex/mc-perf-20261007; D=$W/data; R=$W/twoworker; mkdir -p $R
UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54; BIN=$W/build-main2/motioncorr
O="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --ingest nvcomp"
cd $D
head -n $(grep -n "^Movies/" movies.star | head -1 | cut -d: -f1) movies.star | head -n -1 > $R/hdr.star
grep "^Movies/" movies.star > $R/all.txt
{ cat $R/hdr.star; sed -n '1~2p' $R/all.txt; } > $R/half_a.star
{ cat $R/hdr.star; sed -n '2~2p' $R/all.txt; } > $R/half_b.star
one(){ rm -rf $R/o1; t0=$(date +%s.%N); env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=8 taskset -c 96-103 $BIN --i movies.star --o $R/o1/ $O --j 8 > $R/one.log 2>&1; echo "$(echo "$(date +%s.%N)-$t0"|bc)"; }
two(){ cpa=$1; cpb=$2; j=$3; rm -rf $R/oa $R/ob; t0=$(date +%s.%N)
  env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=$j taskset -c $cpa $BIN --i $R/half_a.star --o $R/oa/ $O --j $j > $R/a.log 2>&1 &
  env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=$j taskset -c $cpb $BIN --i $R/half_b.star --o $R/ob/ $O --j $j > $R/b.log 2>&1 &
  wait; echo "$(echo "$(date +%s.%N)-$t0"|bc)"; }
echo "round,one_8cpu,two_8cpu,two_16cpu,load1"
for r in 1 2 3 4 5; do
  if [ $((r%2)) -eq 1 ]; then a=$(one); b=$(two 96-99 100-103 4); c=$(two 96-103 104-111 8)
  else c=$(two 96-103 104-111 8); b=$(two 96-99 100-103 4); a=$(one); fi
  echo "$r,$a,$b,$c,$(cut -d' ' -f1 /proc/loadavg)"
done
# product identity: union of halves vs single run
n=0; bad=0; for f in $(cd $R/o1 && find . -name "*.mrc"); do n=$((n+1)); src=$R/oa/$f; [ -f $src ] || src=$R/ob/$f; cmp -s <(tail -c +1025 $R/o1/$f) <(tail -c +1025 $src) || bad=$((bad+1)); done; echo "products: $n MRC, $bad differ"
