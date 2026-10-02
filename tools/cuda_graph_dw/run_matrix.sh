#!/bin/bash
# Native harness campaign: settle gate, then the G0/G1 matrix and the exactness
# matrix on one named GPU. Intended to be run under the box flock.
set -u
BIN=$HOME/mc-graph-20261002/tools/cuda_graph_dw/build/graph_dw_probe
OUT=${1:-$HOME/mc-graph-20261002/results}
UUID=${UUID:-GPU-eddb42fe-4f9a-adde-76d3-b924e14add54}
mkdir -p "$OUT"

waited=0
while :; do
  comp=$({ pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l)
  own=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$UUID")
  [ "$comp" -eq 0 ] && [ "$own" -eq 0 ] && break
  [ "$waited" -ge 600 ] && { echo "settle timeout comp=$comp own=$own"; break; }
  sleep 5; waited=$((waited+5))
done
{
  echo "host=$(hostname) date=$(date -Is) settle_wait_s=$waited"
  echo "uuid=$UUID driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
  echo "cuda=$(/usr/local/cuda/bin/nvcc --version | tail -2 | head -1)"
  echo "cufft=$(ls /usr/local/cuda/lib64/libcufft.so.* | tail -1)"
  echo "load=$(cat /proc/loadavg)"
  echo "binary_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
  echo "source_sha256=$(sha256sum "$HOME/mc-graph-20261002/tools/cuda_graph_dw/graph_dw_probe.cu" | cut -d' ' -f1)"
  echo "kernels_sha256=$(grep 'extracted-region sha256' "$HOME/mc-graph-20261002/tools/cuda_graph_dw/build/dw_kernels_generated.cuh")"
} > "$OUT/venue.txt"
cat "$OUT/venue.txt"

export CUDA_VISIBLE_DEVICES=$UUID

run() { # name, args...
  local name=$1; shift
  echo "### $name $*"
  taskset -c 96-103 "$BIN" "$@" > "$OUT/$name.jsonl" 2> "$OUT/$name.err"
  echo "rc=$? lines=$(wc -l < "$OUT/$name.jsonl")"
}

# G0/G1 benchmark: application geometry at three frame counts, plus a small
# geometry where per-operation device work is small enough for submission to show.
run bench_3838x5760_f24  --nx 3838 --ny 5760 --frames 24  --reps 15 --mode bench
run bench_3838x5760_f80  --nx 3838 --ny 5760 --frames 80  --reps 15 --mode bench
run bench_3838x5760_f160 --nx 3838 --ny 5760 --frames 160 --reps 10 --mode bench
run bench_512x512_f160   --nx 512  --ny 512  --frames 160 --reps 15 --mode bench
run bench_256x256_f160   --nx 256  --ny 256  --frames 160 --reps 15 --mode bench
run bench_3838x5760_f24_null --nx 3838 --ny 5760 --frames 24 --reps 15 --mode bench --model null

# Exactness matrix.
for f in 1 2 8 24 80 160; do
  for m in poly null; do
    run exact_3838x5760_f${f}_${m} --nx 3838 --ny 5760 --frames $f --mode exact --model $m
  done
done
run exact_nonsquare_1024x768_f24   --nx 1024 --ny 768  --frames 24 --mode exact
run exact_nonsquare_768x1024_f24   --nx 768  --ny 1024 --frames 24 --mode exact
run exact_oddy_512x511_f24         --nx 512  --ny 511  --frames 24 --mode exact
run exact_oddy_510x513_f24         --nx 510  --ny 513  --frames 24 --mode exact
run exact_dose_zero_f24            --nx 1024 --ny 1024 --frames 24 --mode exact --dose zero
run exact_dose_high_f24            --nx 1024 --ny 1024 --frames 24 --mode exact --dose high
run exact_apix_0p5_f24             --nx 1024 --ny 1024 --frames 24 --mode exact --apix 0.5
run exact_apix_2p0_f24             --nx 1024 --ny 1024 --frames 24 --mode exact --apix 2.0

run faults --nx 1024 --ny 1024 --frames 4 --mode faults
echo "DONE $(date -Is)"
