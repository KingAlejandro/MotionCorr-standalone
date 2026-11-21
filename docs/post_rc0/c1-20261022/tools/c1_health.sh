#!/bin/bash
# Mandatory health propagation. usage: c1_health.sh LABEL cmd...
# Pre-check failure => the command is not run (exit 3). A nonzero post-check turns an otherwise successful command into exit 37
# and the original status is kept when it was already nonzero. Receipts: logs/health-LABEL.{pre,cmd,post}.exit
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
label=$1; shift
L=$C1_SCR/logs; mkdir -p "$L"
"$D/c1_occupancy.sh" "$label-pre"; pre=$?; echo $pre > "$L/health-$label.pre.exit"
[ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre; command not run" >&2; exit 3; }
"$@"; rc=$?; echo $rc > "$L/health-$label.cmd.exit"
"$D/c1_occupancy.sh" "$label-post"; post=$?; echo $post > "$L/health-$label.post.exit"
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (command rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
