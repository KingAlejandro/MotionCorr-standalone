#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Run one named stage with PID/start/finish/exit receipts (adapted from C1 c1_stage.sh). Never retries, never reuses a name.
# usage: stage.sh NAME cmd...   (logs/NAME.{reserved/,cmd,pid,started,log,exit,finished}); an existing artifact refuses with exit 4.
source "$(dirname "$0")/lane.sh" || exit 1
name=$1; shift
case "$name" in ''|*/*|*' '*) echo "bad stage name" >&2; exit 2;; esac
L=$G_SCR/logs; mkdir -p "$L"
for ext in reserved cmd pid started log exit finished; do
  [ -e "$L/$name.$ext" ] && { echo "stage $name already has .$ext; refusing" >&2; exit 4; }
done
mkdir "$L/$name.reserved" 2>/dev/null || { echo "stage $name reserved concurrently; refusing" >&2; exit 4; }
echo "$$ $(date -u +%FT%TZ)" > "$L/$name.reserved/owner"
printf '%q ' "$@" > "$L/$name.cmd"; echo >> "$L/$name.cmd"
echo $$ > "$L/$name.pid"; date -u +%FT%TZ > "$L/$name.started"
"$@" > "$L/$name.log" 2>&1
rc=$?
echo $rc > "$L/$name.exit"; date -u +%FT%TZ > "$L/$name.finished"
exit $rc
