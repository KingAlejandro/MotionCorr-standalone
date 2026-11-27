#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Lane occupancy and GPU1 health by UUID. Exit 3 on a compute process on GPU1, an uncorrected ECC error,
# or a pending/failed row remap. usage: health.sh LABEL   (logs/health-LABEL.txt)
set -u
source "$(dirname "$0")/lane.sh" || exit 1
mkdir -p "$G_SCR/logs"; o="$G_SCR/logs/health-$1.txt"
q=$(nvidia-smi --id=$G_GPU_UUID --query-gpu=uuid,name,ecc.errors.uncorrected.volatile.total,remapped_rows.pending,remapped_rows.failure,memory.used,utilization.gpu --format=csv,noheader)
apps=$(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader | grep "$G_GPU_UUID")
{
  date -u +%FT%TZ; hostname; echo "gpu1: $q"; echo "gpu1 compute apps: ${apps:-none}"
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
  echo "--- all compute apps"; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader
  echo "--- lock holders"; for f in $G_GPU_LOCK $G_BUILD_LOCK /tmp/motioncorr-bench.lock /tmp/motioncorr-i61-cpu-14-15.lock $G_CPU_LOCK; do echo "$f: $(fuser $f 2>&1 | tr -s ' ')"; done
  echo "--- processes last on CPUs 14,15"; ps -eo pid,user,psr,pcpu,etimes,args --sort=-pcpu | awk 'NR==1 || $3==14 || $3==15' | head -12 | cut -c1-220
  df -h /mnt/clathrin | tail -1; du -sh $G_SCR 2>/dev/null
} > "$o" 2>&1
IFS=, read -r uuid name ecc rpend rfail mem util <<< "$q"
bad=""
[ "$(echo $uuid)" = "$G_GPU_UUID" ] || bad="$bad identity"
[ -n "$apps" ] && bad="$bad compute-process"
[ "$(echo $ecc)" = "0" ] || bad="$bad ecc=$ecc"
case "$(echo $rpend)" in No|no|0) ;; *) bad="$bad remap-pending=$rpend";; esac
case "$(echo $rfail)" in No|no|0) ;; *) bad="$bad remap-failure=$rfail";; esac
echo "health $1: ${bad:-PASS}" | tee -a "$o" >&2
[ -z "$bad" ] || exit 3
