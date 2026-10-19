#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Verify the script checksums in a separate SSH call before launching.
set -u
W=$HOME/mc-post-rc0-s1
lane=$1
families=$2
older=${3:-}
mkdir -p "$W/launch-$lane"
exec 9>"$W/launch-$lane/controller.lock"
flock -n 9 || exit 75
[ ! -e "$W/launch-$lane/job.id" ] || exit 76
salloc -p gpu-devel --gres=gpu:1 --cpus-per-task=8 --mem=48G --no-shell --time=12:00:00 --exclude=cn031,cn055,cn3063,gn0001 --nodelist=gn0005 --job-name="mcs1-$lane" > "$W/launch-$lane/salloc.log" 2>&1
rc=$?
[ "$rc" = 0 ] || { echo "$rc" > "$W/launch-$lane/exit"; exit "$rc"; }
job=$(sed -n 's/.*Granted job allocation \([0-9]*\).*/\1/p' "$W/launch-$lane/salloc.log" | tail -1)
[[ "$job" =~ ^[0-9]+$ ]] || { echo 77 > "$W/launch-$lane/exit"; exit 77; }
echo "$job" > "$W/launch-$lane/job.id"
srun --jobid="$job" --overlap --cpus-per-task=8 bash -c 'export TMPDIR=/tmp; exec /usr/bin/python3 "$HOME/mc-post-rc0-s1/tools/scarf_campaign_recover_v1.py" "$@"' bash --families "$families" --cache-roots /tmp/mc-s1-3645672/data,/tmp/mc-s1-3645644/data --skip-movies e10474f4-00,e10474f4-01,e10164-00 > "$W/launch-$lane/step.log" 2>&1
rc=$?
echo "$rc" > "$W/launch-$lane/exit"
scancel "$job" > "$W/launch-$lane/release.log" 2>&1
echo "$?" > "$W/launch-$lane/release.exit"
exit "$rc"
