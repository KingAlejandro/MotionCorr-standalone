#!/bin/bash
# Host-to-device bytes per route, from Nsight rather than from arithmetic.
#
# Byte counts are contention-immune: the same payload reports the same number
# whatever else the box is doing, which transfer *time* does not. One movie per
# arm; the per-movie figure is what scales.
set -u
W=/home/alex/mc-inputs-20261002
MASK=96-103
BIN=$1; GPU=$2; TAG=$3; shift 3
for v in "$@"; do
  out=$W/results/nsys_${TAG}__${v}
  rm -rf "$out" "$out.nsys-rep" "$out.sqlite"; mkdir -p "$out"
  ( cd $W/inputs/$v && \
    taskset -c $MASK nsys profile --trace=cuda --cuda-memory-usage=false \
      --force-overwrite=true -o "$out" \
      "$BIN" --i movies1.star --o "$out/" --use_own --dose_weighting \
      --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 \
      --gainref Movies/gain.mrc --seed 1 --j 8 --gpu "$GPU" \
      --ingest_witness "$out/route_witness.txt" > "$out/nsys.stdout" 2>&1 )
  h2d=$(nsys stats --report cuda_gpu_mem_size_sum --format csv "$out.nsys-rep" 2>/dev/null \
        | awk -F, '/HtoD/ {print $2; exit}')
  d2h=$(nsys stats --report cuda_gpu_mem_size_sum --format csv "$out.nsys-rep" 2>/dev/null \
        | awk -F, '/DtoH/ {print $2; exit}')
  printf 'H2D tag=%s variant=%-20s route=%s h2d_MiB=%s d2h_MiB=%s\n' \
    "$TAG" "$v" "$(awk '{print $2}' "$out/route_witness.txt" 2>/dev/null | head -1)" \
    "${h2d:-NA}" "${d2h:-NA}"
  rm -rf "$out"
done
