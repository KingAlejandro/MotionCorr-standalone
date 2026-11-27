#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Hold the GPU1 correctness lock (nonblocking, exit 5 on contention) through pre-health, the command and post-health.
# usage: gpu_locked.sh LABEL cmd...   exit 3 pre-health failure (command not run), 37 post-health failure after success.
set -u
D=$(dirname "$0"); source "$D/lane.sh" || exit 1
label=$1; shift
exec 9>"$G_GPU_LOCK"; flock -n 9 || { echo "GPU1 correctness lock contended; stopping"; fuser $G_GPU_LOCK; exit 5; }
"$D/health.sh" "$label-pre" || exit 3
"$@"; rc=$?
"$D/health.sh" "$label-post" || { echo "post-run health failed (command rc=$rc)"; [ $rc -eq 0 ] && rc=37; }
exit $rc
