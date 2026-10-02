#!/bin/bash
# Confirmation campaign: adds a sustained warm-up and a live SM-clock witness
# (persistence mode is off on this host, so a cold device measures slow), the
# corrected node-update control, and per-arm Nsight counts.
set -u
HERE=$HOME/mc-graph-20261002/tools/cuda_graph_dw
BIN=$HERE/build/graph_dw_probe
OUT=${1:-$HOME/mc-graph-20261002/results2}
mkdir -p "$OUT"

# Pick a GPU with no foreign compute app.
UUID=""
for u in $(nvidia-smi --query-gpu=uuid --format=csv,noheader); do
  n=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -c "$u")
  if [ "$n" -eq 0 ]; then UUID=$u; break; fi
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

# Clock/utilisation witness. Bounded by timeout and killed by the trap, so it
# can never outlive the campaign and dead-hold the box lock.
timeout 3600 nvidia-smi --query-gpu=timestamp,clocks.sm,utilization.gpu \
        --format=csv,noheader -i "$IDX" -lms 250 > "$OUT/clocks.csv" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

{
  echo "host=$(hostname) date=$(date -Is) settle_wait_s=$waited"
  echo "gpu_index=$IDX uuid=$UUID"
  nvidia-smi --query-gpu=name,driver_version,persistence_mode,clocks.max.sm --format=csv -i "$IDX"
  echo "cuda=$(/usr/local/cuda/bin/nvcc --version | tail -2 | head -1)"
  echo "cufft=$(ls /usr/local/cuda/lib64/libcufft.so.* | tail -1)"
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
# 3710x3838 is the tutorial corrected-image geometry; the 3838x5760 rows are a
# larger case, and the small geometries bound where submission could ever matter.
run bench_3710x3838_f24  --nx 3710 --ny 3838 --frames 24  --reps 21 --mode bench $W
run bench_3710x3838_f80  --nx 3710 --ny 3838 --frames 80  --reps 15 --mode bench $W
run bench_3710x3838_f160 --nx 3710 --ny 3838 --frames 160 --reps 11 --mode bench $W
run bench_3838x5760_f24  --nx 3838 --ny 5760 --frames 24  --reps 21 --mode bench $W
run bench_3838x5760_f80  --nx 3838 --ny 5760 --frames 80  --reps 15 --mode bench $W
run bench_3838x5760_f160 --nx 3838 --ny 5760 --frames 160 --reps 11 --mode bench $W
run bench_512x512_f160   --nx 512  --ny 512  --frames 160 --reps 21 --mode bench $W
run bench_256x256_f160   --nx 256  --ny 256  --frames 160 --reps 21 --mode bench $W
run bench_3838x5760_f24_null --nx 3838 --ny 5760 --frames 24 --reps 21 --mode bench --model null $W

for f in 1 2 8 24 80 160; do for m in poly null; do
  run exact_3710x3838_f${f}_${m} --nx 3710 --ny 3838 --frames $f --mode exact --model $m
  run exact_3838x5760_f${f}_${m} --nx 3838 --ny 5760 --frames $f --mode exact --model $m
done; done
run exact_nonsquare_1024x768_f24 --nx 1024 --ny 768  --frames 24 --mode exact
run exact_nonsquare_768x1024_f24 --nx 768  --ny 1024 --frames 24 --mode exact
run exact_oddy_512x511_f24       --nx 512  --ny 511  --frames 24 --mode exact
run exact_oddy_510x513_f24       --nx 510  --ny 513  --frames 24 --mode exact
run exact_dose_zero_f24          --nx 1024 --ny 1024 --frames 24 --mode exact --dose zero
run exact_dose_high_f24          --nx 1024 --ny 1024 --frames 24 --mode exact --dose high
run exact_apix_0p5_f24           --nx 1024 --ny 1024 --frames 24 --mode exact --apix 0.5
run exact_apix_2p0_f24           --nx 1024 --ny 1024 --frames 24 --mode exact --apix 2.0
run faults --nx 1024 --ny 1024 --frames 4 --mode faults

# Per-arm Nsight counts at the application geometry.
mkdir -p "$OUT/nsys"
for arm in prod async g0 greuse; do
  echo "### nsys $arm"
  nsys profile --trace=cuda -o "$OUT/nsys/$arm" --force-overwrite true \
    taskset -c 96-103 "$BIN" --nx 3710 --ny 3838 --frames 24 --reps 3 \
    --mode bench --only "$arm" --warmup_ms 1000 > "$OUT/nsys/$arm.run" 2>&1
  nsys stats --report cuda_api_sum --report cuda_gpu_kern_sum \
             --report cuda_gpu_mem_time_sum --format csv \
             -o "$OUT/nsys/$arm" "$OUT/nsys/$arm.nsys-rep" > "$OUT/nsys/$arm.stats" 2>&1
done
echo "DONE $(date -Is)"
