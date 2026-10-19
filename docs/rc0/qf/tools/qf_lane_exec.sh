#!/bin/bash
# Per-run lane wrapper for harnesses that take --binary (QF items 13; ported from #204's gpu3run.sh/cpurun.sh).
# Runs $MC_BIN with the given arguments in the QF lane: waits while the bench lock is held (probe only),
# holds $QF_GPU_LOCK for this one process, waits for no foreign compute process on $QF_GPU_UUID,
# pins CUDA_VISIBLE_DEVICES=$QF_GPU_UUID and taskset $QF_CPUS. QF_LANE_CPU_ONLY=1: CPU-only build, no GPU
# lock or device. MC_RSS_FILE (optional) receives peak RSS in KiB. Appends "sha256 argv" to $QF_LANE_LOG.
set -u
: "${MC_BIN:?}" "${QF_CPUS:?}" "${QF_GPU_UUID:?}" "${QF_GPU_LOCK:?}"
[ -n "${QF_LANE_LOG:-}" ] && echo "$(sha256sum "$MC_BIN" | cut -c1-64) $*" >> "$QF_LANE_LOG"
until flock -n /tmp/motioncorr-bench.lock true; do sleep 60; done
run() {
  if [ -n "${MC_RSS_FILE:-}" ]; then /usr/bin/time -f %M -o "$MC_RSS_FILE" "$@"; else "$@"; fi
}
if [ "${QF_LANE_CPU_ONLY:-0}" = 1 ]; then
  CUDA_VISIBLE_DEVICES= run taskset -c "$QF_CPUS" "$MC_BIN" "$@"; exit $?
fi
exec 9>"$QF_GPU_LOCK"
flock 9
while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$QF_GPU_UUID"; do sleep 5; done
CUDA_VISIBLE_DEVICES=$QF_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID run taskset -c "$QF_CPUS" "$MC_BIN" "$@"
