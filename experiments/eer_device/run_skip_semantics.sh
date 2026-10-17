#!/bin/sh
# Can the device reproduce the host's per-fraction skip semantics? Grouped products on the mutated movie, device
# --on_corrupt skip vs EERRenderer (which skips the same fractions with a warning), plus the negative control
# (--on_corrupt fail leaves the failed fractions' partial counts in the frames and must NOT match), a chunked
# run, a uint16 run, memcheck of the skip path, and the cost of the skip path on real movies.
# usage: run_skip_semantics.sh <build-dir> <fixture-dir> <inputs.txt> <out-dir>
set -u
B=${1:?}; FX=${2:?}; IN=${3:?}; OUT=${4:?}
HERE=$(cd "$(dirname "$0")" && pwd)
CS=${COMPUTE_SANITIZER:-/usr/local/cuda/bin/compute-sanitizer}
mkdir -p "$OUT"
path() { awk -v k="$1" '$1==k{print $4}' "$IN"; }
for u in 1 2 -1; do
  $HERE/run_lane.sh $B/eer_device_exp compare --eer $FX/mut48.eer --grouping 8 --upsampling $u --timing 0 --on_corrupt skip --label mut48-skip-u$u > $OUT/mut48.skip.u$u.json 2> $OUT/mut48.skip.u$u.err
  $HERE/run_lane.sh $B/eer_device_exp compare --eer $FX/mut48.eer --grouping 8 --upsampling $u --timing 0 --on_corrupt fail --label mut48-fail-u$u > $OUT/mut48.fail.u$u.json 2> $OUT/mut48.fail.u$u.err
done
$HERE/run_lane.sh $B/eer_device_exp compare --eer $FX/mut48.eer --grouping 8 --upsampling 1 --timing 0 --on_corrupt skip --cap_mib 4 --label mut48-skip-chunked-u1 > $OUT/mut48.skip.chunked.u1.json 2>/dev/null
$HERE/run_lane.sh $B/eer_device_exp compare --eer $FX/mut48.eer --grouping 8 --upsampling 1 --timing 0 --on_corrupt skip --out u16 --arena 0 --label mut48-skip-u16-u1 > $OUT/mut48.skip.u16.u1.json 2>/dev/null
$HERE/run_lane.sh $B/eer_device_exp compare --eer $FX/base48.eer --grouping 8 --upsampling 1 --timing 0 --on_corrupt skip --label base48-skip-u1 > $OUT/base48.skip.u1.json 2>/dev/null
for u in 1 2; do
  $HERE/run_lane.sh $CS --tool memcheck --error-exitcode 99 $B/eer_device_exp compare --eer $FX/mut48.eer --grouping 8 --upsampling $u --verify 0 --timing 0 --on_corrupt skip > $OUT/mut48.skip.u$u.memcheck.out 2> $OUT/mut48.skip.u$u.memcheck.log; echo $? > $OUT/mut48.skip.u$u.memcheck.rc
done
# cost of the skip path (no failed fractions): device-only, bench lock, NUMA pinned
for spec in "f3 40" "f4 40"; do
  set -- $spec
  for mode in fail skip; do
    $HERE/run_lane.sh --bench $B/eer_device_exp compare --eer "$(path $1)" --grouping $2 --upsampling 1 --label cost-$1-$mode --verify 0 --host_timing 0 --pairs 8 --on_corrupt $mode > $OUT/cost-$1-$mode.json 2>/dev/null
  done
done
echo skip done
