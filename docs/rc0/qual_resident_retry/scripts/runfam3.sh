#!/bin/bash
# usage: runfam3.sh <binary> <family e10641u|e10216|tutorial> <tag> [extra motioncorr args...]
# env: MCENV="K=V ..."  GPU=2  CPUS=80-87
# Waits (poll 60 s) while /tmp/motioncorr-bench.lock is held (never touches the holder),
# re-checks under the GPU lock, samples NVML per-process VRAM every ~0.1 s into vram.csv.
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
bin=$1; fam=$2; tag=$3; shift 3
GPU=${GPU:-2}; CPUS=${CPUS:-80-87}
case $GPU in 2) UUID=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598;; 3) UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d;; esac
case $fam in
 e10641|e10641u) FO="--dose_per_frame 1.0 --gainref gain.mrc --expected_frames 70";;
 e10216) FO="--dose_per_frame 1.0 --expected_frames 59";;
 tutorial) FO="--dose_per_frame 1.277 --gainref gain.mrc --expected_frames 24";;
esac
out=$S/runs/$tag; [ -e $out ] && { echo "exists $out"; exit 9; }
mkdir -p $S/runs/$tag.side; side=$S/runs/$tag.side
cd $S/inputs/corpus/$fam
export S bin UUID CPUS FO side out MCENV
export ARGS="$*"
inner() {
 flock -n /tmp/motioncorr-bench.lock true || exit 75
 echo "START $(date -u +%FT%TZ) bin=$bin sha=$(sha256sum $bin | cut -d' ' -f1) cpus=$CPUS uuid=$UUID"
 ( while true; do nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader,nounits | grep "^$UUID" | sed "s/^/$(date +%s.%N), /"; sleep 0.05; done ) > $side/vram.csv 2>/dev/null &
 SP=$!
 taskset -c $CPUS env CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8 $MCENV \
  /usr/bin/time -v $bin --use_own --dose_weighting --bfactor 150 --seed 1 $FO --patch_x 5 --patch_y 5 \
  --i movies.star --o $out/ --j 8 --gpu 0 --ingest_witness $side/witness.txt $ARGS 2> $side/run.stderr
 rc=$?
 kill $SP; wait $SP 2>/dev/null
 echo "rc=$rc"; echo "END $(date -u +%FT%TZ)"
 exit $rc
}
export -f inner
while true; do
 until flock -n /tmp/motioncorr-bench.lock true; do echo "$(date -u +%T) bench lock held; waiting" >> $side/bench-wait.log; sleep 60; done
 nvidia-smi --query-compute-apps=gpu_uuid,pid,name --format=csv > $side/pre-nvidia-smi.txt
 flock /tmp/motioncorr-gpu$GPU-correctness.lock bash -c inner > $side/run.stdout
 rc=$?
 [ $rc -ne 75 ] && break
done
echo done $tag rc=$(grep '^rc=' $side/run.stdout)
