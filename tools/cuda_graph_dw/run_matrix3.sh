#!/bin/bash
# Re-measurement after the harness wall fix (host-side digest excluded).
set -u
HERE=$HOME/mc-graph-20261002/tools/cuda_graph_dw
BIN=$HERE/build/graph_dw_probe
OUT=${1:-$HOME/mc-graph-20261002/results3}
mkdir -p "$OUT"
UUID=""
for u in $(nvidia-smi --query-gpu=uuid --format=csv,noheader); do
  n=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$u")
  [ "$n" -eq 0 ] && { UUID=$u; break; }
done
[ -z "$UUID" ] && { echo "no idle GPU"; exit 1; }
IDX=$(nvidia-smi --query-gpu=index,uuid --format=csv,noheader | grep "$UUID" | cut -d, -f1 | tr -d ' ')
waited=0
while :; do
  comp=$({ pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l)
  own=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$UUID")
  [ "$comp" -eq 0 ] && [ "$own" -eq 0 ] && break
  [ "$waited" -ge 900 ] && { echo "settle timeout comp=$comp own=$own"; break; }
  sleep 5; waited=$((waited+5))
done
timeout 2400 nvidia-smi --query-gpu=timestamp,clocks.sm,utilization.gpu \
        --format=csv,noheader -i "$IDX" -lms 250 > "$OUT/clocks.csv" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT
{
  echo "host=$(hostname) date=$(date -Is) settle_wait_s=$waited"
  echo "gpu_index=$IDX uuid=$UUID"
  echo "load=$(cat /proc/loadavg)"
  echo "binary_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
  echo "probe_src_sha256=$(sha256sum "$HERE/graph_dw_probe.cu" | cut -d' ' -f1)"
  grep 'extracted-region sha256' "$HERE/build/dw_kernels_generated.cuh"
} > "$OUT/venue.txt"
cat "$OUT/venue.txt"
export CUDA_VISIBLE_DEVICES=$UUID
run() { local name=$1; shift; echo "### $name $*"
  taskset -c 96-103 "$BIN" "$@" > "$OUT/$name.jsonl" 2> "$OUT/$name.err"; echo "  rc=$?"; }
W="--warmup_ms 3000"
run bench_3710x3838_f24  --nx 3710 --ny 3838 --frames 24  --reps 21 --mode bench $W
run bench_3710x3838_f80  --nx 3710 --ny 3838 --frames 80  --reps 15 --mode bench $W
run bench_3710x3838_f160 --nx 3710 --ny 3838 --frames 160 --reps 11 --mode bench $W
run bench_3710x3838_f24_null --nx 3710 --ny 3838 --frames 24 --reps 21 --mode bench --model null $W
run bench_512x512_f160   --nx 512  --ny 512  --frames 160 --reps 21 --mode bench $W
run bench_256x256_f160   --nx 256  --ny 256  --frames 160 --reps 21 --mode bench $W
echo "MATRIX3 DONE $(date -Is)"
