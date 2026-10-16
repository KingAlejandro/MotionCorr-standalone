#!/bin/bash
# Fixed per-process cost, main vs candidate steps. Run under flock + taskset 96-103.
# usage: fixed_ab.sh <outdir> <arm=binary>...      (rounds/rotation fixed below)
set -u
R=$1; shift
W=/home/alex/mc-small; D=$W/data96
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
      --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --profile_device_timing 0 --skip_report_pdf)
export CUDA_VISIBLE_DEVICES=$U CUDA_DEVICE_ORDER=PCI_BUS_ID
mkdir -p $R; cd $D
declare -A BIN; ARMS=()
for a in "$@"; do BIN[${a%%=*}]=${a#*=}; ARMS+=(${a%%=*}); done
NARM=${#ARMS[@]}
ncomp() { { pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l; }
napps() { nvidia-smi --id=$U --query-compute-apps=pid --format=csv,noheader | grep -c . ; }
settle() { local t0=$SECONDS
  while [ $(( SECONDS - t0 )) -lt 900 ]; do [ "$(ncomp)" -eq 0 ] && [ "$(napps)" -eq 0 ] && break; sleep 2; done
  echo "settle_wait_s=$(( SECONDS - t0 )) compilers=$(ncomp) gpu_apps=$(napps)"; }
lane_jiffies() { awk "/^cpu(9[6-9]|10[0-3]) /{s+=\$2+\$3+\$4+\$7+\$8} END{print s}" /proc/stat; }
run() { # tag arm star
  local tag=$1 arm=$2 star=$3; local out=$R/$tag; rm -rf $out; mkdir -p $out
  settle > $out/settle.txt; uptime > $out/load.txt
  local j0=$(lane_jiffies) t0=$(date +%s%N)
  /usr/bin/time -v -o $out/time.txt taskset -c 96-103 ${BIN[$arm]} "${OPTS[@]}" --i $star --o $out/out/ --profile $out/profile.jsonl > $out/stdout.txt 2>&1
  local rc=$? t1=$(date +%s%N) j1=$(lane_jiffies)
  local nmrc=$(find $out/out -name "*.mrc" | wc -l)
  echo "{\"tag\":\"$tag\",\"arm\":\"$arm\",\"rc\":$rc,\"proc_wall_ms\":$(( (t1 - t0) / 1000000 )),\"lane_busy_jiffies\":$(( j1 - j0 )),\"n_mrc\":$nmrc}" | tee -a $R/runs.jsonl
  rm -rf $out/out
}
echo "start $(date -Is) thp=$(cat /sys/kernel/mm/transparent_hugepage/enabled) load=$(cut -d' ' -f1-3 /proc/loadavg)" | tee $R/header.txt
for a in "${ARMS[@]}"; do sha256sum ${BIN[$a]} | cut -c1-16 | sed "s/^/$a sha256=/" >> $R/header.txt; done
nvidia-smi --id=$U --query-gpu=name,driver_version,persistence_mode,clocks.sm --format=csv >> $R/header.txt
# discarded warm-up: one run per arm and size (cold binary / page cache)
for a in "${ARMS[@]}"; do run warm12_$a $a movies12_fixed116.star; done
for a in "${ARMS[@]}"; do run warm96_$a $a movies.star; done
ROUNDS=${ROUNDS:-5}
for round in $(seq 1 $ROUNDS); do
  for n in 12 96; do
    star=movies12_fixed116.star; [ $n = 96 ] && star=movies.star
    for k in $(seq 0 $((NARM-1))); do
      a=${ARMS[$(( (k + round) % NARM ))]}
      run r${round}_n${n}_$a $a $star
    done
  done
done
echo "end $(date -Is)" | tee -a $R/header.txt
