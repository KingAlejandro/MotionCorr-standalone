#!/bin/bash
# Host-to-device bytes per movie from Nsight Systems (byte counts are contention-immune).
# usage: h2d.sh <tag> <binary> <variant>...   one movie, default --ingest auto, GPU3, CPUs 72-79.
set -u
wait_bench() { while ! flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held by another session; waiting 60 s ($(date -u +%FT%TZ))" >&2; sleep 60; done; }
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
TAG=$1; BIN=$2; shift 2
GPUUUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
RES=$D/results/h2d; mkdir -p $RES
for v in "$@"; do
  wait_bench
  out=$D/out/nsys_${TAG}__${v}; rm -rf $out $out.nsys-rep $out.sqlite; mkdir -p $out
  ( cd $D/inputs/$v
    head -n $(( $(grep -n '^data_movies' movies.star | cut -d: -f1) + 6 )) movies.star > movies1.star
    flock -w 7200 9
    CUDA_VISIBLE_DEVICES=$GPUUUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c 72-79 \
      nsys profile --trace=cuda --cuda-memory-usage=false --sample=none --cpuctxsw=none \
        --force-overwrite=true -o $out \
        $BIN --i movies1.star --o $out/ --use_own --dose_weighting --dose_per_frame 1.277 \
        --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --gpu 0 \
        --ingest_witness $RES/${TAG}__${v}.witness > $RES/${TAG}__${v}.stdout 2>&1
    echo "rc=$?" > $RES/${TAG}__${v}.rc
  ) 9>/tmp/motioncorr-gpu3-correctness.lock
  nsys stats --report cuda_gpu_mem_size_sum --format csv $out.nsys-rep > $RES/${TAG}__${v}.memsize.csv 2>/dev/null
  nsys stats --force-export=true --report cuda_gpu_kern_sum --format csv $out.nsys-rep > $RES/${TAG}__${v}.kern.csv 2>/dev/null
  h2d=$(awk -F'"' '/HtoD/ {print $2; exit}' $RES/${TAG}__${v}.memsize.csv)
  printf 'H2D tag=%s variant=%s route=%s rc=%s total_MB=%s\n' "$TAG" "$v" \
     "$(awk '{print $2}' $RES/${TAG}__${v}.witness | head -1)" "$(cat $RES/${TAG}__${v}.rc)" "$(awk -F, '/HtoD/{print $1; exit}' $RES/${TAG}__${v}.memsize.csv)" | tee -a $RES/h2d_summary.txt
  rm -rf $out
done
