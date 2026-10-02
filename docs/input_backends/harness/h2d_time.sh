#!/bin/bash
# Host-to-device transfer time per route, from the same captures as the bytes.
set -u
printf '%-24s %-6s %14s %7s\n' variant arm H2D_total_ms ops
for r in "$1"/nsys_*.nsys-rep; do
  tag=$(basename "$r" .nsys-rep); tag=${tag#nsys_}
  arm=${tag%%__*}; var=${tag#*__}
  line=$(nice -19 taskset -c 110 nsys stats --report cuda_gpu_mem_time_sum "$r" 2>/dev/null \
         | grep "memcpy Host-to-Device")
  ns=$(echo "$line" | awk '{gsub(",","",$2); print $2}')
  n=$(echo "$line" | awk '{gsub(",","",$3); print $3}')
  printf '%-24s %-6s %14.1f %7s\n' "$var" "$arm" "$(echo "scale=1; ${ns:-0}/1000000" | bc)" "${n:-NA}"
done
