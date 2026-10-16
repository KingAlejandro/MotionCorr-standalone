#!/bin/bash
# Base 116eb04a vs candidate, default options, --profile. Run under:
#   flock -w 3600 /tmp/motioncorr-bench.lock taskset -c 96-103 bash timing.sh
# Paired design: 5 reps per movie count, arm order alternating by rep, one discarded warm-up per arm and count.
set -u
W=/home/alex/mc-small/lfe; D=/home/alex/mc-small/data96
BIN_base=$W/build-base/motioncorr; BIN_cand=$W/build-cand/motioncorr
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
R=$W/runs/timing; rm -rf $R; mkdir -p $R
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
      --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --profile_device_timing 0)
export CUDA_VISIBLE_DEVICES=$U CUDA_DEVICE_ORDER=PCI_BUS_ID
cd $D
ncomp() { { pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l; }
napps() { nvidia-smi --id=$U --query-compute-apps=pid --format=csv,noheader | grep -c . ; }
settle() {
  local t0=$SECONDS
  while [ $(( SECONDS - t0 )) -lt 600 ]; do
    [ "$(ncomp)" -eq 0 ] && [ "$(napps)" -eq 0 ] && break; sleep 2
  done
  echo "settle_wait_s=$(( SECONDS - t0 )) compilers=$(ncomp) gpu_apps=$(napps)"
}
lane_jiffies() { awk "/^cpu(9[6-9]|10[0-3]) /{s+=\$2+\$3+\$4+\$7+\$8} END{print s}" /proc/stat; }
run() {  # tag arm star
  local tag=$1 arm=$2 star=$3 B=BIN_$2
  local out=$R/$tag; rm -rf $out; mkdir -p $out
  settle > $out/settle.txt; uptime > $out/load.txt
  local j0=$(lane_jiffies) t0=$(date +%s%N)
  taskset -c 96-103 ${!B} "${OPTS[@]}" --i $star --o $out/out/ --profile $out/profile.jsonl > $out/stdout.txt 2>&1
  local rc=$? t1=$(date +%s%N) j1=$(lane_jiffies)
  echo "{\"tag\":\"$tag\",\"arm\":\"$arm\",\"rc\":$rc,\"proc_wall_ms\":$(( (t1 - t0) / 1000000 )),\"lane_busy_jiffies\":$(( j1 - j0 )),\"n_mrc\":$(find $out/out -name '*.mrc' | wc -l),\"settle\":\"$(cat $out/settle.txt)\"}" | tee -a $R/runs.jsonl
  rm -rf $out/out
}
echo "start $(date -Is) base=$(sha256sum $BIN_base | cut -c1-16) cand=$(sha256sum $BIN_cand | cut -c1-16) thp=$(cat /sys/kernel/mm/transparent_hugepage/enabled) gs=$(gs --version)" | tee $R/header.txt
nvidia-smi --id=$U --query-gpu=name,driver_version,persistence_mode,clocks.sm --format=csv >> $R/header.txt
for n in 12 96; do
  star=movies12_fixed116.star; [ $n = 96 ] && star=movies.star
  run warm_n${n}_base base $star; run warm_n${n}_cand cand $star
done
for rep in 1 2 3 4 5; do
  for n in 12 96; do
    star=movies12_fixed116.star; [ $n = 96 ] && star=movies.star
    if [ $(( rep % 2 )) = 1 ]; then order="base cand"; else order="cand base"; fi
    pos=1
    for arm in $order; do run r${rep}_n${n}_${arm}_p$pos $arm $star; pos=$((pos+1)); done
  done
done
echo "end $(date -Is)" | tee -a $R/header.txt
