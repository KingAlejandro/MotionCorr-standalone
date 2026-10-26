#!/bin/bash
# i8 occupancy + health for one or more GPUs (by ordinal into the C1_GPU<n>_UUID table; identity is checked by UUID inside the health check).
# usage: c1_occ.sh LABEL GPUS    e.g. c1_occ.sh a13-pre 3     c1_occ.sh mg-pre 0,1,2,3
# Writes $C1_SCR/logs/occupancy-LABEL.txt (all GPUs' memory/apps, lock holders, bench lock holder, CPU 96-103 users, disk) and runs
# c1_health_check.py once per requested GPU (identity, ECC, row remap, retired pages, no compute process). Exit 0 = every GPU healthy;
# otherwise the first nonzero health exit (3 compute process present, 4/6 unusable or anomalous). Kernel Xid inspection is separate (c1_xid.sh).
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
label=$1; gpus=${2:-3}
mkdir -p "$C1_SCR/logs"
o="$C1_SCR/logs/occupancy-$label.txt"
{
  date -u +%FT%TZ; hostname
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
  echo "--- compute apps (all GPUs)"; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader
  echo "--- locks held by anyone (fuser)"; for f in /tmp/motioncorr-gpu0-correctness.lock /tmp/motioncorr-gpu1-correctness.lock /tmp/motioncorr-gpu2-correctness.lock /tmp/motioncorr-gpu3-correctness.lock /tmp/motioncorr-build.lock /tmp/motioncorr-bench.lock; do echo "$f: $(fuser $f 2>&1 | tr -s ' ')"; done
  echo "--- processes last scheduled on CPUs 96-103"; ps -eo pid,user,psr,pcpu,etimes,args --sort=-pcpu | awk 'NR==1 || ($3>=96 && $3<=103)' | head -14 | cut -c1-200
  uptime; df -h /mnt/clathrin | tail -1
} > "$o" 2>&1
rc=0
for g in ${gpus//,/ }; do
  eval "u=\$C1_GPU${g}_UUID"
  C1_GPU_UUID=$u "$C1_PY" "$(dirname "$0")/c1_health_check.py" "$label-gpu$g" >> "$o" 2>&1
  r=$?; echo "gpu$g health exit $r" >> "$o"; [ $r -ne 0 ] && [ $rc -eq 0 ] && rc=$r
done
tail -2 "$o" >&2
exit $rc
