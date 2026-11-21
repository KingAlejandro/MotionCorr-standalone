#!/bin/bash
# One-shot operational wrapper for the frozen cpu1c chain (not part of the frozen inputs; its hash is in the launch receipts).
# Holds the outer CPU lease for the whole chain, runs the unchanged chain as a child so its full exit status is recorded.
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb; L=$SC/logs/cpu1c-launch; LOCK=/tmp/motioncorr-c1-cpu8-9.lock
set -C
echo $$ > $L/wrapper.pid; date -u +%FT%TZ > $L/wrapper.started; id -u > $L/wrapper.uid; echo "$0 $*" > $L/wrapper.argv
awk '/Cpus_allowed_list/{print $2}' /proc/self/status > $L/wrapper.cpus
exec 9>"$LOCK"
if ! flock -n 9; then { echo "outer CPU lease contended"; date -u +%FT%TZ; } > $L/lease.contended; echo 7 > $L/wrapper.exit; exit 7; fi
{ echo "outer CPU lease $LOCK acquired by wrapper pid $$"; date -u +%FT%TZ; } > $L/lease.acquired
bash $SC/chain-cpu1c.sh > $SC/logs/chain-cpu1c.out 2>&1
rc=$?
echo $rc > $L/wrapper.exit; date -u +%FT%TZ > $L/wrapper.finished
exit $rc
