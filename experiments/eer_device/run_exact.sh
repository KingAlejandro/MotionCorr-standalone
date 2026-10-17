#!/bin/sh
# Exactness-only pass (no timing): every pixel of every group vs EERRenderer, all 15 corpus configurations, float and uint16 output.
# usage: run_exact.sh <build-dir> <inputs.txt> <out-dir>
set -u
B=${1:?}; IN=${2:?}; OUT=${3:?}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
path() { awk -v k="$1" '$1==k{print $4}' "$IN"; }
v() { label=$1; key=$2; g=$3; u=$4; shift 4
  $HERE/run_lane.sh $B/eer_device_exp compare --eer "$(path $key)" --grouping $g --upsampling $u --label $label --timing 0 "$@" > $OUT/$label.verify.json 2>> $OUT/$label.log
  echo "$label rc=$? $(python3 -c "import json;d=json.load(open('$OUT/$label.verify.json'));print(d['verify']['verdict'])" 2>&1)"; }
for spec in "f3 40 f3-g40" "f3 48 f3-g48" "f4 40 f4-g40" "f4 50 f4-g50" "g 49 g-g49" "g 40 g-g40"; do
  set -- $spec
  for u in 1 2 -1; do
    case "$2-$3$u" in 48-f3-g48-1|50-f4-g50-1|40-g-g40-1) continue;; esac
    v $3-u$u-float $1 $2 $u
  done
done
for spec in "f3 40 f3-g40" "f4 40 f4-g40" "g 49 g-g49"; do set -- $spec; v $3-u1-u16 $1 $2 1 --out u16 --arena 0; done
echo exact done
