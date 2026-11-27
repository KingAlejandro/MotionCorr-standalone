#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# CPU-only lane occupancy (no nvidia-smi, no GPU query). Exit 3 when CPUs 14-15 are more than 50% busy
# over a 3 s /proc/stat sample, or the scratch exceeds the 8 GiB cap. usage: occupancy_cpu.sh LABEL
set -u
source "$(dirname "$0")/../tools/lane.sh" || exit 1
mkdir -p "$G_SCR/logs"; o="$G_SCR/logs/occupancy-$1.txt"
busy() { awk '/^cpu1[45] /{b+=$2+$3+$4+$7+$8+$9; t+=$2+$3+$4+$5+$6+$7+$8+$9} END{print b, t}' /proc/stat; }
read b0 t0 < <(busy); sleep 3; read b1 t1 < <(busy)
pct=$(( (b1 - b0) * 100 / ( (t1 - t0) > 0 ? (t1 - t0) : 1 ) ))
kib=$(du -sk "$G_SCR" | cut -f1)
{
  date -u +%FT%TZ; hostname; echo "cpu14-15 busy over 3 s: ${pct}%"; echo "scratch KiB: $kib (cap 8388608)"
  echo "--- lock holders"; for f in $G_BUILD_LOCK $G_CPU_LOCK /tmp/motioncorr-i61-cpu-14-15.lock /tmp/motioncorr-bench.lock; do echo "$f: $(fuser $f 2>&1 | tr -s ' ')"; done
  echo "--- processes last on CPUs 14,15"; ps -eo pid,user,psr,pcpu,etimes,args --sort=-pcpu | awk 'NR==1 || $3==14 || $3==15' | head -12 | cut -c1-220
  df -h /mnt/clathrin | tail -1
} > "$o" 2>&1
bad=""; [ $pct -le 50 ] || bad="$bad cpu-busy=$pct%"; [ $kib -le 8388608 ] || bad="$bad scratch-over-cap"
echo "occupancy $1: ${bad:-PASS}" | tee -a "$o" >&2
[ -z "$bad" ]
