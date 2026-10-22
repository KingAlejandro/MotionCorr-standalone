#!/bin/bash
# Run one named stage with PID/start/finish/exit receipts. Never retries, never shares a name.
# usage: c1_stage.sh NAME cmd...   (logs/NAME.{reserved/,cmd,pid,started,log,exit,finished})
# The name is reserved atomically (mkdir) BEFORE anything is written or spawned. Any existing reservation or artifact (started/partial/finished,
# live or dead) refuses the launch with exit 4: reconcile the earlier PID and exit receipt by hand, keep its receipts, and use a distinct stage name
# in a distinct frozen iteration. Reservations are never removed by this script.
source "$(dirname "$0")/c1_env.sh" || exit 1
name=$1; shift
case "$name" in ''|*/*|*' '*) echo "bad stage name" >&2; exit 2;; esac
L=$C1_SCR/logs; mkdir -p "$L"
for ext in reserved cmd pid started log exit finished; do
  [ -e "$L/$name.$ext" ] && { echo "stage $name already has .$ext; refusing (reconcile PID/exit, then freeze a new iteration)" >&2; exit 4; }
done
mkdir "$L/$name.reserved" 2>/dev/null || { echo "stage $name reserved by a concurrent launcher; refusing" >&2; exit 4; }
echo "$$ $(date -u +%FT%TZ)" > "$L/$name.reserved/owner"
printf '%q ' "$@" > "$L/$name.cmd"; echo >> "$L/$name.cmd"
echo $$ > "$L/$name.pid"; date -u +%FT%TZ > "$L/$name.started"
"$@" > "$L/$name.log" 2>&1
rc=$?
echo $rc > "$L/$name.exit"; date -u +%FT%TZ > "$L/$name.finished"
exit $rc
