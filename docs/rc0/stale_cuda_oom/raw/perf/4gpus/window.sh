#!/bin/bash
# One timing window on 4GPUs: holds the bench lock and the GPU3 lock for the whole window (<= 45 min),
# payload on GPU3 (by UUID) + CPUs 88-95, driver and samplers on CPUs 120-123, mpstat and nvidia-smi
# sampled every 10 s. usage: window.sh <workload> <data dir> <motioncorr args...>
set -u
name=$1; data=$2; shift 2
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; E=$W/timing4/$name; mkdir -p $E
UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
export CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES
exec 8>/tmp/motioncorr-bench.lock; t0=$(date +%s); flock 8; echo "bench lock acquired after $(( $(date +%s)-t0 )) s" > $E/window.txt
exec 9>/tmp/motioncorr-gpu3-correctness.lock; flock 9
while nvidia-smi -i $UUID --query-compute-apps=pid --format=csv,noheader | grep -q .; do sleep 10; done
{ echo "window start $(date -u +%FT%TZ)"; uptime; cat /sys/kernel/mm/transparent_hugepage/enabled
  nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,clocks.sm,clocks.max.sm,persistence_mode --format=csv
  echo "main $(sha256sum $W/build-main-nvcomp/motioncorr)"; echo "fix  $(sha256sum $W/build-fix-nvcomp/motioncorr)"
  echo "src main=$(git -C $W/src-main rev-parse HEAD) fix=$(git -C $W/src-fix rev-parse HEAD)"; } >> $E/window.txt
taskset -c 120-123 mpstat -P ALL 10 > $E/mpstat.txt 2>&1 & S1=$!
taskset -c 120-123 nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv -l 10 > $E/nvidia-smi.csv 2>&1 & S2=$!
( while sleep 10; do echo "$(date -u +%T) $(nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader | tr '\n' ';')"; done ) > $E/compute-apps.txt 2>&1 & S3=$!
taskset -c 120-123 python3 $W/wd11_pairs.py --name $name --a $W/build-main-nvcomp/motioncorr --b $W/build-fix-nvcomp/motioncorr \
  --data $data --cpus 88-95 --src $W/src-fix --out $E --gpu-uuid $UUID ${EXTRA_DRIVER:-} -- "$@" > $E/driver.out 2>&1
rc=$?
kill $S1 $S2 $S3 2>/dev/null
{ echo "driver rc=$rc"; echo "window end $(date -u +%FT%TZ)"; uptime; } >> $E/window.txt
flock -u 9; flock -u 8
tail -3 $E/driver.out
