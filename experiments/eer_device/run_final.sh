#!/bin/sh
# Final-binary chain: exactness, malformed inputs, skip semantics, and the three default timing series (host vs device pairs).
# usage: run_final.sh <build-dir> <fixture-dir> <inputs.txt> <out-dir>
set -u
B=${1:?}; FX=${2:?}; IN=${3:?}; OUT=${4:?}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT/exact $OUT/malformed $OUT/skipsem $OUT/timing
sha256sum $B/eer_device_exp $B/eer_device_exp_asan > $OUT/binary-sha256.txt
sh $HERE/run_exact.sh $B $IN $OUT/exact > $OUT/exact.log 2>&1
sh $HERE/run_malformed.sh $B $FX $OUT/malformed > $OUT/malformed.log 2>&1
sh $HERE/run_skip_semantics.sh $B $FX $IN $OUT/skipsem > $OUT/skipsem.log 2>&1
path() { awk -v k="$1" '$1==k{print $4}' "$IN"; }
for spec in "f3 40" "f4 40" "g 49"; do
  set -- $spec
  python3 $HERE/lane_precheck.py GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 96-103 10 0.25 > $OUT/timing/$1-u1.precheck.json 2>&1
  LANE_GPU_SAMPLES=$OUT/timing/$1-u1.gpu-samples.csv $HERE/run_lane.sh --bench $B/eer_device_exp compare --eer "$(path $1)" --grouping $2 --upsampling 1 --label final-$1-u1 --verify 0 --pairs 8 > $OUT/timing/$1-u1.timing.json 2>> $OUT/timing/log
done
echo final done > $OUT/final.done
