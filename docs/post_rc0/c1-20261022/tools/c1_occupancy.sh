#!/bin/bash
# Record lane occupancy; exit 3 when a foreign compute process is on the lane GPU.
# usage: c1_occupancy.sh LABEL   (writes $C1_SCR/logs/occupancy-LABEL.txt)
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
mkdir -p "$C1_SCR/logs"
o="$C1_SCR/logs/occupancy-$1.txt"
{
  date -u +%FT%TZ; hostname
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
  echo "--- compute apps"; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader
  echo "--- locks held by anyone (fuser)"; for f in /tmp/motioncorr-gpu3-correctness.lock /tmp/motioncorr-build.lock /tmp/motioncorr-bench.lock; do echo "$f: $(fuser $f 2>&1 | tr -s ' ')"; done
  echo "--- processes last scheduled on CPUs 8,9"; ps -eo pid,user,psr,pcpu,etimes,args --sort=-pcpu | awk 'NR==1 || $3==8 || $3==9' | head -12 | cut -c1-200
  df -h /mnt/clathrin | tail -1
} > "$o" 2>&1
if nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$C1_GPU_UUID"; then echo "foreign compute process on lane GPU" >&2; exit 3; fi
exit 0
