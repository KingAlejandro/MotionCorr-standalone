#!/bin/bash
# usage: runfam.sh <binary> <family e10641|e10216|tutorial> <tag> [extra motioncorr args...]
# env: MCENV="K=V ..." extra environment (e.g. MC_FAULT...), GPU=2 (default)
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
bin=$1; fam=$2; tag=$3; shift 3
GPU=${GPU:-2}
case $GPU in 2) UUID=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598;; 3) UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d;; esac
case $fam in
 e10641|e10641u) FO="--dose_per_frame 1.0 --gainref gain.mrc --expected_frames 70";;
 e10216) FO="--dose_per_frame 1.0 --expected_frames 59";;
 tutorial) FO="--dose_per_frame 1.277 --gainref gain.mrc --expected_frames 24";;
esac
out=$S/runs/$tag; [ -e $out ] && { echo "exists $out"; exit 9; }
mkdir -p $out/../$tag.side; side=$S/runs/$tag.side
cd $S/inputs/corpus/$fam
{
 echo "START $(date -u +%FT%TZ) bin=$bin sha=$(sha256sum $bin | cut -d' ' -f1)"
 nvidia-smi --query-compute-apps=gpu_uuid,pid,name --format=csv
 /usr/bin/time -v flock /tmp/motioncorr-gpu$GPU-correctness.lock \
  taskset -c ${CPUS:-80-87} env CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8 $MCENV \
  $bin --use_own --dose_weighting --bfactor 150 --seed 1 $FO --patch_x 5 --patch_y 5 \
  --i movies.star --o $out/ --j 8 --gpu 0 --ingest_witness $side/witness.txt "$@"
 echo "rc=$?"
 echo "END $(date -u +%FT%TZ)"
} > $side/run.stdout 2> $side/run.stderr
echo done $tag rc=$(grep '^rc=' $side/run.stdout)
