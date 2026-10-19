#!/bin/bash
# Per-run wrapper: wait for the bench lock to be free (never touch its holder), then hold the GPU3 lane lock
# for this one motioncorr process only; CPUs 88-95, GPU3 by UUID. MC_RSS_FILE (optional) receives peak RSS in KiB.
BIN=${MC_BIN:?}
UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
until flock -n /tmp/motioncorr-bench.lock true; do sleep 60; done
exec 9>/tmp/motioncorr-gpu3-correctness.lock
flock 9
for i in $(seq 1 120); do
  nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q $UUID || break
  sleep 5
done
if [ -n "$MC_RSS_FILE" ]; then
  CUDA_VISIBLE_DEVICES=3 taskset -c 88-95 /usr/bin/time -f %M -o "$MC_RSS_FILE" "$BIN" "$@"
else
  CUDA_VISIBLE_DEVICES=3 taskset -c 88-95 "$BIN" "$@"
fi
