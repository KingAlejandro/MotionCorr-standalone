#!/bin/bash
# Existing QF drivers (docs/rc0/qf/tools), lane GPU3/CPUs 8-9, single-GPU rows only. usage: c1_item.sh 12|9cuda|9nvcomp|13
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
export QF_W=$C1_SCR; cd $C1_SCR
Q=$C1_SCR/src/docs/rc0/qf/tools
"$(dirname "$0")/c1_occupancy.sh" item-$1-pre || exit 3
case $1 in
  12) taskset -c $C1_CPUS $C1_PY $Q/item12_retry.py;;
  9cuda) flock -n $C1_GPU_LOCK taskset -c $C1_CPUS $C1_PY $Q/run_compact_ingest_support_matrix.py --binary build-cuda/motioncorr --device $C1_GPU_UUID --workdir matrix-cuda --json matrix-cuda.json;;
  9nvcomp) flock -n $C1_GPU_LOCK taskset -c $C1_CPUS $C1_PY $Q/run_compact_ingest_support_matrix.py --binary build-nvcomp/motioncorr --device $C1_GPU_UUID --workdir matrix-nvcomp --json matrix-nvcomp.json;;
  13) bash $Q/item13_mrc.sh;;
  *) echo unknown; exit 2;;
esac
rc=$?
"$(dirname "$0")/c1_occupancy.sh" item-$1-post
exit $rc
