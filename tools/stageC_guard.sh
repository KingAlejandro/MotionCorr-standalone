#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Stage C resource guard: the Stage A/B `guard()` from stageAB_chain.sh, logic unchanged, as a standalone script so the
# driver can run it before every producer against live resources. It reads nvidia-smi, /proc/stat, ps, df and free;
# a lease claim alone is not accepted. Usage: stageC_guard.sh LABEL NEED_GPU(0|1)
# Environment (all required): STAGEC_GPU2 (UUID), STAGEC_FOREIGN_PID, STAGEC_SCRATCH.
# Exit: 0 pass; 11 other compute app on the granted GPU; 12 granted GPU utilisation > 50 %; 13 a core of 80-87 > 50 % busy.
GPU2=${STAGEC_GPU2:?}; FOREIGN_PID=${STAGEC_FOREIGN_PID:?}; S=${STAGEC_SCRATCH:?}
label=$1; need_gpu=$2
ts() { date -u +%FT%TZ; }
stop() { echo "STOP $1: $2 ($(ts))"; exit "$3"; }

echo "== guard $label $(ts)"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory,process_name --format=csv,noheader
a=$(mktemp); grep "^cpu[0-9]" /proc/stat > $a; sleep 3
busy=$(grep "^cpu[0-9]" /proc/stat | paste -d" " $a - | awk '{u1=$2+$3+$4+$7+$8; t1=u1+$5+$6; u2=$13+$14+$15+$18+$19; t2=u2+$16+$17; d=t2-t1; n=$1; sub("cpu","",n); if (n>=80 && n<=87 && d>0) printf "%s %.0f\n", $1, 100*(u2-u1)/d}')
rm -f $a
echo "cpu80-87 busy%: $(echo $busy | tr '\n' ' ')"
max=$(echo "$busy" | awk '{if ($2>m) m=$2} END {print m+0}')
echo "processes currently running on cpu80-87:"; ps -eo psr,stat,pcpu,user,pid,args --no-headers | awk '$1>=80 && $1<=87 && $2 ~ /^R/' | cut -c1-140
df -h "$S" | tail -1; free -g | sed -n 2p; du -sh "$S" 2>/dev/null
[ "$max" -gt 50 ] && stop guard "a core in 80-87 is >50% busy ($max%)" 13
if [ "$need_gpu" = 1 ]; then
  others=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | awk -F", " -v g=$GPU2 -v f=$FOREIGN_PID '$2==g && $1!=f')
  [ -n "$others" ] && stop guard "other compute app on GPU2: $others" 11
  util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i $GPU2)
  [ "$util" -gt 50 ] && stop guard "GPU2 utilisation $util% > 50%" 12
fi
echo "guard $label passed"
