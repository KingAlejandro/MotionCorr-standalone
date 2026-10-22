#!/bin/bash
# Run one named stage with PID/start/finish/exit receipts. Never retries.
# usage: c1_stage.sh NAME cmd...   (logs/NAME.{cmd,pid,started,log,exit,finished})
source "$(dirname "$0")/c1_env.sh" || exit 1
name=$1; shift
L=$C1_SCR/logs; mkdir -p "$L"
[ -e "$L/$name.exit" ] && { echo "stage $name already has an exit receipt; refusing to rerun (freeze a new iteration)" >&2; exit 4; }
printf '%q ' "$@" > "$L/$name.cmd"; echo >> "$L/$name.cmd"
echo $$ > "$L/$name.pid"; date -u +%FT%TZ > "$L/$name.started"
"$@" > "$L/$name.log" 2>&1
rc=$?
echo $rc > "$L/$name.exit"; date -u +%FT%TZ > "$L/$name.finished"
exit $rc
