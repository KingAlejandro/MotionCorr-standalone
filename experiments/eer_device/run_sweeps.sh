#!/bin/sh
# Device-only sweeps: reader threads (wall and CPU cost), ring chunk size, decode block size.
# Same lane, bench lock + NUMA pinning, no host arm.
# usage: run_sweeps.sh <build-dir> <inputs.txt> <out-dir> [pairs]
set -u
B=${1:?}; IN=${2:?}; OUT=${3:?}; P=${4:-6}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
path() { awk -v k="$1" '$1==k{print $4}' "$IN"; }
run() { # label key grouping extra...
  label=$1; key=$2; g=$3; shift 3
  $HERE/run_lane.sh --bench $B/eer_device_exp compare --eer "$(path $key)" --grouping $g --upsampling 1 --label $label --verify 0 --host_timing 0 --pairs $P "$@" > $OUT/$label.json 2>> $OUT/sweeps.log
}
for spec in "f3 40" "f4 40" "g 49"; do
  set -- $spec
  for t in 1 2 4 8; do run threads-$1-t$t $1 $2 --read_threads $t; done
  for m in 16 256; do run ring-$1-m$m $1 $2 --ring_mib $m; done
done
for blk in 32 64 128 256; do run block-f4-b$blk f4 40 --block $blk; done
echo sweeps done >> $OUT/sweeps.log
