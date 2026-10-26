#!/bin/bash
# nvCOMP-ingest poisoning rows on GPU3 (CPUs 96-103): the GPU3 lease is taken nonblocking and held for the whole phase, the bench lock is only probed and recorded,
# health is checked before and after the phase by this wrapper and around every arm by the driver. usage: c1_ingest.sh pre|fault WORKDIR [PRE_WORKDIR]  (through c1_stage.sh)
set -u
D=$(cd "$(dirname "$0")" && pwd); source "$D/c1_env.sh" || exit 1
phase=$1; work=$2; pre=${3:-}
export QF_W=$C1_SCR; cd $C1_SCR
exec 9>>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 lease contended; stopping (no retry)"; exit 5; }
( exec 5>>$C1_BENCH_LOCK; if flock -n 5; then echo "bench lock probe: free"; else echo "bench lock probe: HELD (not waited on, not touched)"; fi ) | tee $C1_SCR/logs/ingest-$phase.bench-probe
"$D/c1_occ.sh" ingest-$phase-pre 3; p=$?; [ $p -eq 0 ] || { echo "pre-run health failed rc=$p"; exit 3; }
sha256sum $C1_SCR/build-ingest-fault/motioncorr_ingest_fault > $C1_SCR/logs/ingest-$phase.binary.sha256
CUDA_VISIBLE_DEVICES=$C1_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c $C1_CPUS $C1_PY $D/c1_ingest_poison.py \
  --binary $C1_SCR/build-ingest-fault/motioncorr_ingest_fault --workdir "$work" --phase $phase ${pre:+--pre-dir "$pre"}
rc=$?
"$D/c1_occ.sh" ingest-$phase-post 3; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
