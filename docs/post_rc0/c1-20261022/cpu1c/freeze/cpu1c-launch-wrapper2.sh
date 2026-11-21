#!/bin/bash
# One-shot operational wrapper v2 for the frozen cpu1c chain (not a frozen input; its hash goes into the launch receipts).
# v2 fix: the lock file is opened without noclobber (v1 set -C made `exec 9>lock` fail on an existing lock file, which it then misreported as contention).
# Holds the outer CPU lease for the whole chain and runs the unchanged chain as a child so its full exit status is recorded.
# Environment overrides exist only for the harmless self-test; the real launch uses the defaults.
SC=${CPU1C_SC:-/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb}; L=${CPU1C_LAUNCH_DIR:-$SC/logs/cpu1c-launch2}; LOCK=${CPU1C_LOCK:-/tmp/motioncorr-c1-cpu8-9.lock}
CHAIN=${CPU1C_CHAIN:-$SC/chain-cpu1c.sh}; OUT=${CPU1C_CHAIN_OUT:-$SC/logs/chain-cpu1c.out}
echo $$ > $L/wrapper.pid; date -u +%FT%TZ > $L/wrapper.started; id -u > $L/wrapper.uid; echo "$0 $*" > $L/wrapper.argv
awk '/Cpus_allowed_list/{print $2}' /proc/self/status > $L/wrapper.cpus
exec 9>>"$LOCK" || { echo "cannot open the lease file" > $L/lease.error; echo 8 > $L/wrapper.exit; exit 8; }
if ! flock -n 9; then { echo "outer CPU lease contended"; date -u +%FT%TZ; } > $L/lease.contended; echo 7 > $L/wrapper.exit; exit 7; fi
{ echo "outer CPU lease $LOCK acquired by wrapper pid $$"; date -u +%FT%TZ; } > $L/lease.acquired
bash "$CHAIN" > "$OUT" 2>&1
rc=$?
echo $rc > $L/wrapper.exit; date -u +%FT%TZ > $L/wrapper.finished
exit $rc
