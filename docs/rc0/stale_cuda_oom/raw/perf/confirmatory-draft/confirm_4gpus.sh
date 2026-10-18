#!/bin/bash
# DRAFT / NOT RUN. 4GPUs fallback for the confirmatory design (rule.txt): four windows, in the declared
# order, each holding the bench lock and the GPU3 lock for its whole duration (<= 45 min) and releasing
# them in between. Payload GPU3 by UUID + CPUs 88-95; driver and samplers on CPUs 120-123.
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; E=$W/confirm4; SRC=$W/src-head
UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
MAIN=$W/build-main-nvcomp/motioncorr; FIX=$W/build-fix-nvcomp/motioncorr
TUT=/home/alex/motioncorr-validation-20261011-vm/tutorial-data; E10216=$W/perf-e10216
G="--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp"
EL="--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact"
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES
mkdir -p $E; cp $SRC/docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft/{rule.txt,confirm_pairs.py} $E/
echo "binaries: $(sha256sum $MAIN | cut -c1-64) $(sha256sum $FIX | cut -c1-64)" > $E/provenance.txt

window() { # window <workload> <n> <index> <data> <args...>
  local w=$1 n=$2 i=$3 data=$4; shift 4
  local O=$E/$w; mkdir -p $O; local L=$O/window$i-host
  exec 8>/tmp/motioncorr-bench.lock; local t0=$(date +%s); flock 8
  exec 9>/tmp/motioncorr-gpu3-correctness.lock; flock 9
  while nvidia-smi -i $UUID --query-compute-apps=pid --format=csv,noheader | grep -q .; do sleep 10; done
  { echo "bench lock wait $(( $(date +%s)-t0 )) s; start $(date -u +%FT%TZ)"; uptime; } > $L.txt
  taskset -c 120-123 mpstat -P ALL 10 > $L.mpstat 2>&1 & local s1=$!
  taskset -c 120-123 nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used --format=csv -l 10 > $L.nvsmi.csv 2>&1 & local s2=$!
  taskset -c 120-123 python3 $E/confirm_pairs.py run --workload $w --n $n --windows 2 --window $i \
      --a $MAIN --b $FIX --data $data --cpus 88-95 --src $SRC --out $O --gpu-uuid $UUID -- "$@" > $O/window$i.driver.out 2>&1
  echo "driver rc=$?; end $(date -u +%FT%TZ)" >> $L.txt; uptime >> $L.txt
  kill $s1 $s2; gzip $L.mpstat; flock -u 9; flock -u 8
}
window tutG 256 1 $TUT $G
window e10216L 176 1 $E10216 $EL
window tutG 256 2 $TUT $G
window e10216L 176 2 $E10216 $EL
for w in tutG e10216L; do python3 $E/confirm_pairs.py combine --workload $w --out $E/$w --src $SRC; done
