#!/bin/bash
# A13: QF item 13 (raw integer MRC staging, #204 harness) unedited at its native --j 8, lane CPUs 96-103, GPU3 (the harness' qf_lane_exec.sh holds
# the GPU3 lease per run and waits on a held bench lock; this wrapper first probes the lease nonblocking and stops on contention) and records
# health before and after (post failure -> exit 37 even if the driver passed). usage: c1_a13.sh   (run through c1_stage.sh)
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
export QF_W=$C1_SCR; cd $C1_SCR
( flock -n 9 || exit 5 ) 9>>"$C1_GPU_LOCK" || { echo "GPU3 lease contended; stopping (no retry)"; exit 5; }
"$D/c1_occ.sh" a13-pre 3; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
Q=$C1_SCR/src/docs/rc0/qf/tools
sha256sum $Q/item13_mrc.sh $Q/qf_lane_exec.sh $Q/grade_item13.py $Q/harness_mrc/*.py $Q/item_records/mrc_204.json $C1_SCR/build-nvcomp/motioncorr $C1_SCR/build-cpu/motioncorr > $C1_SCR/logs/a13-identity.sha256
taskset -c $C1_CPUS bash $Q/item13_mrc.sh; rc=$?
"$D/c1_occ.sh" a13-post 3; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
