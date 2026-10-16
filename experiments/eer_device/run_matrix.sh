#!/bin/sh
# Exactness and timing matrix for the three corpus movies. Run on 4GPUs.
# usage: run_matrix.sh <build-dir> <inputs.txt> <out-dir> [pairs]
# Exactness (every pixel vs EERRenderer) runs under the GPU0 lock only. Timing runs hold the bench lock only for the
# timed series of one case, NUMA-pinned (numactl --cpunodebind=1 --membind=1 + taskset 96-103), pairs alternating AB/BA with
# one discarded warm-up per arm. A series with foreign CPU > 0.25 cores (pre-sample or during the series) is kept as
# <label>.timing.attemptN.json and retried (max 3); failed attempts are never deleted. GPUs 1-3 are sampled during each series.
set -u
B=${1:?}; IN=${2:?}; OUT=${3:?}; P=${4:-8}
HERE=$(cd "$(dirname "$0")" && pwd)
UUID=${LANE_GPU_UUID:-GPU-eddb42fe-4f9a-adde-76d3-b924e14add54}
mkdir -p "$OUT"
path() { awk -v k="$1" '$1==k{print $4}' "$IN"; }
verify_case() { # label key grouping ups [extra args]
  label=$1; key=$2; g=$3; u=$4; shift 4
  $HERE/run_lane.sh $B/eer_device_exp compare --eer "$(path $key)" --grouping $g --upsampling $u --label $label --timing 0 "$@" > $OUT/$label.verify.json 2>> $OUT/$label.log
  echo "$label verify rc=$? $(python3 -c "import json;d=json.load(open('$OUT/$label.verify.json'));print(d.get('verify',{}).get('verdict'),d.get('admission',{}).get('verdict'))" 2>&1)" | tee -a $OUT/matrix.log
}
time_case() { # label key grouping ups [extra args]
  label=$1; key=$2; g=$3; u=$4; shift 4; a=1
  while [ $a -le 3 ]; do
    python3 $HERE/lane_precheck.py $UUID 96-103 10 0.25 > $OUT/$label.precheck$a.json 2>>$OUT/$label.log; pc=$?
    if [ $pc -ne 0 ]; then echo "$label precheck failed (attempt $a)" | tee -a $OUT/matrix.log; a=$((a+1)); sleep 30; continue; fi
    LANE_GPU_SAMPLES=$OUT/$label.gpu-samples$a.csv $HERE/run_lane.sh --bench $B/eer_device_exp compare --eer "$(path $key)" --grouping $g --upsampling $u --label $label --verify 0 --pairs $P "$@" > $OUT/$label.timing.attempt$a.json 2>>$OUT/$label.log
    rc=$?
    ok=$(python3 $HERE/series_check.py $OUT/$label.timing.attempt$a.json $OUT/$label.gpu-samples$a.csv)
    echo "$label timing attempt $a rc=$rc $ok" | tee -a $OUT/matrix.log
    case "$ok" in ok*) okflag=1;; *) okflag=0;; esac
    if [ $rc -eq 0 ] && [ $okflag = 1 ]; then cp $OUT/$label.timing.attempt$a.json $OUT/$label.timing.json; return; fi
    a=$((a+1))
  done
  echo "$label timing FAILED after 3 attempts" | tee -a $OUT/matrix.log
}
# exactness: all 15 configurations with the integration-shaped output (float, borrowed arena); u16 on the defaults
for spec in "f3 40 f3-g40" "f3 48 f3-g48" "f4 40 f4-g40" "f4 50 f4-g50" "g 49 g-g49" "g 40 g-g40"; do
  set -- $spec
  for u in 1 2 -1; do
    case "$2-$3$u" in 48-f3-g48-1|50-f4-g50-1|40-g-g40-1) continue;; esac
    verify_case $3-u$u-float $1 $2 $u
  done
done
for spec in "f3 40 f3-g40" "f4 40 f4-g40" "g 49 g-g49"; do set -- $spec; verify_case $3-u1-u16 $1 $2 1 --out u16 --arena 0; done
# admission refusals: the same 144-group 8192x8192 case on emulated smaller cards, and with a larger declared reserve
verify_case f4-g40-u2-admit-40GiB f4 40 2 --vram_limit_mib 40960
verify_case f4-g40-u2-admit-reserve-8GiB f4 40 2 --reserve_mib 8192
verify_case f4-g40-u2-admit-reserve-12GiB f4 40 2 --reserve_mib 12288
# timing: default groupings, balanced pairs; host arm skipped where the retained uint16 stack would not fit node 1's free RAM
for spec in "f3 40 f3-g40" "f4 40 f4-g40" "g 49 g-g49"; do set -- $spec; time_case $3-u1 $1 $2 1; done
time_case f3-g40-u2 f3 40 2
time_case g-g49-u2 g 49 2
time_case f3-g40-u-1 f3 40 -1
time_case f4-g40-u-1 f4 40 -1
time_case g-g49-u-1 g 49 -1
time_case f4-g40-u2-devonly f4 40 2 --host_timing 0
echo matrix done | tee -a $OUT/matrix.log
