#!/bin/bash
# Existing QF drivers, adapted only where resources/expectations require it; lane GPU3/CPUs 8-9. usage: c1_item.sh 12|12ds|9cuda|9nvcomp
# 12   c1_item12.py single-GPU rows (task-local --j 2 and C1-derived retry expectations; legacy #207 comparisons reported separately)
# 12ds c1_item12.py --dataset-single-gpu (1-worker healthy and 1-worker poisoned dataset arms; no second device needed)
# 9*   QF compact-ingest matrix with --threads 2
# Not offered: item 13 (its vendored real-data harness hardcodes --j 8, more than the 2-CPU lane): UNRUN unless the parent grants CPUs.
# Health: pre-check stops the run; a failed post-check makes the wrapper exit 37 even if the driver passed.
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
export QF_W=$C1_SCR; cd $C1_SCR
Q=$C1_SCR/src/docs/rc0/qf/tools
"$D/c1_occupancy.sh" item-$1-pre; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
case $1 in
  12) taskset -c $C1_CPUS $C1_PY $D/c1_item12.py;;
  12ds) taskset -c $C1_CPUS $C1_PY $D/c1_item12.py --dataset-single-gpu;;
  9cuda) flock -n $C1_GPU_LOCK taskset -c $C1_CPUS $C1_PY $Q/run_compact_ingest_support_matrix.py --binary build-cuda/motioncorr --device $C1_GPU_UUID --workdir matrix-cuda --json matrix-cuda.json --threads 2;;
  9nvcomp) flock -n $C1_GPU_LOCK taskset -c $C1_CPUS $C1_PY $Q/run_compact_ingest_support_matrix.py --binary build-nvcomp/motioncorr --device $C1_GPU_UUID --workdir matrix-nvcomp --json matrix-nvcomp.json --threads 2;;
  *) echo unknown; exit 2;;
esac
rc=$?
"$D/c1_occupancy.sh" item-$1-post; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
