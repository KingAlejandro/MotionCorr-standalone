#!/bin/bash
# Slow-round attribution: main vs step 2 alone vs step 1 alone, every run profiled,
# with system-wide THP/compaction counters around each process.
# Run with the bench lock held and the lane pinned (taskset -c 96-103); takes the
# GPU0 correctness lock itself for the measured part.
# usage: stall_ab.sh <outdir> <arm=binary>...   env: R24 (rounds at 24 movies), R96
set -u
R=$1; shift
S=/dev/shm/mcs2; IN=$S/in
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
      --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --profile_device_timing 0 --skip_report_pdf)
KEYS="compact_stall compact_fail compact_success thp_fault_alloc thp_fault_fallback compact_migrate_scanned compact_free_scanned allocstall_normal allocstall_movable pgmajfault"
export CUDA_VISIBLE_DEVICES=$U CUDA_DEVICE_ORDER=PCI_BUS_ID
mkdir -p $R; cd $IN
declare -A BIN; ARMS=()
for a in "$@"; do BIN[${a%%=*}]=${a#*=}; ARMS+=(${a%%=*}); done
NARM=${#ARMS[@]}
ncomp() { { pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l; }
napps() { nvidia-smi --id=$U --query-compute-apps=pid --format=csv,noheader | grep -c . ; }
settle() { local t0=$SECONDS
  while [ $(( SECONDS - t0 )) -lt 900 ]; do [ "$(ncomp)" -eq 0 ] && [ "$(napps)" -eq 0 ] && break; sleep 2; done
  echo "settle_wait_s=$(( SECONDS - t0 )) compilers=$(ncomp) gpu_apps=$(napps)"; }
lane_jiffies() { awk '/^cpu(9[6-9]|10[0-3]) /{s+=$2+$3+$4+$7+$8} END{print s}' /proc/stat; }
vm() { awk -v keys="$KEYS" 'BEGIN{n=split(keys,k," "); for(i=1;i<=n;i++) w[k[i]]=1} ($1 in w){printf "%s=%s ", $1, $2}' /proc/vmstat; }
huge_blocks() { awk '/Normal/{for(i=5;i<=NF;i++){o=i-5; if(o>=9) s+=$i*2^(o-9)}} END{print s}' /proc/buddyinfo; }
run() { # tag arm star
  local tag=$1 arm=$2 star=$3; local out=$R/$tag; rm -rf $out; mkdir -p $out
  settle > $out/settle.txt; uptime > $out/load.txt
  echo "free_2m_blocks=$(huge_blocks)" > $out/vm_before.txt; vm >> $out/vm_before.txt
  local j0=$(lane_jiffies) t0=$(date +%s%N)
  /usr/bin/time -v -o $out/time.txt taskset -c 96-103 ${BIN[$arm]} "${OPTS[@]}" --i $star --o $S/scratch/$tag/ --profile $out/profile.jsonl > $out/stdout.txt 2>&1
  local rc=$? t1=$(date +%s%N) j1=$(lane_jiffies)
  vm > $out/vm_after.txt
  local nmrc=$(find $S/scratch/$tag -name "*.mrc" | wc -l)
  echo "{\"tag\":\"$tag\",\"arm\":\"$arm\",\"rc\":$rc,\"proc_wall_ms\":$(( (t1 - t0) / 1000000 )),\"lane_busy_jiffies\":$(( j1 - j0 )),\"n_mrc\":$nmrc}" | tee -a $R/runs.jsonl
  rm -rf $S/scratch/$tag
}
{ echo "start $(date -Is) load=$(cut -d' ' -f1-3 /proc/loadavg) uptime=$(cut -d' ' -f1 /proc/uptime)"
  for f in enabled defrag khugepaged/defrag; do echo "thp/$f: $(cat /sys/kernel/mm/transparent_hugepage/$f)"; done
  echo "compaction_proactiveness=$(cat /proc/sys/vm/compaction_proactiveness) extfrag_threshold=$(cat /proc/sys/vm/extfrag_threshold)"
  echo "kernel=$(uname -r)"; free -g | head -2; cat /proc/buddyinfo
  for a in "${ARMS[@]}"; do echo "$a sha256=$(sha256sum ${BIN[$a]} | cut -c1-16) bin=${BIN[$a]}"; done
  nvidia-smi --id=$U --query-gpu=name,driver_version,persistence_mode,clocks.sm --format=csv; } | tee $R/header.txt
for a in "${ARMS[@]}"; do run warm24_$a $a movies24.star; done
for round in $(seq 1 ${R24:-12}); do
  for k in $(seq 0 $((NARM-1))); do a=${ARMS[$(( (k + round) % NARM ))]}; run r${round}_n24_$a $a movies24.star; done
done
for round in $(seq 1 ${R96:-4}); do
  for k in $(seq 0 $((NARM-1))); do a=${ARMS[$(( (k + round) % NARM ))]}; run r${round}_n96_$a $a movies.star; done
done
echo "end $(date -Is)" | tee -a $R/header.txt
