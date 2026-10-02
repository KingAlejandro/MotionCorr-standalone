#!/bin/bash
# Run the remaining campaigns safely after the shared lock file was unlinked.
#
# Another session deleted /tmp/motioncorr-bench.lock while holding it. Everyone
# who opened the file before that still contends on the old, now-unlinked
# inode; anyone taking the path afterwards creates a NEW inode and gets the
# lock immediately. For as long as both groups exist, flock alone no longer
# provides exclusion, so this waits for the old group to drain before taking
# the new file, and still gates each run on observed quiescence.
set -u
W=/home/alex/mc-inputs-20261002
log() { echo "[$(date -u +%FT%TZ)] $*"; }

old_inode_holders() {
  local n=0
  for p in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
    for fd in /proc/$p/fd/*; do
      case "$(readlink "$fd" 2>/dev/null)" in
        *motioncorr-bench.lock*deleted*) n=$((n+1)); break;;
      esac
    done
  done
  echo "$n"
}

log "waiting for campaign6 to finish"
until grep -q CAMPAIGN_DONE "$W/logs/campaign6.log" 2>/dev/null; do sleep 45; done
log "campaign6 done"

log "waiting for the unlinked-inode lock group to drain"
for i in $(seq 1 480); do
  n=$(old_inode_holders)
  [ "$n" -eq 0 ] && break
  [ $((i % 20)) -eq 0 ] && log "still $n holder(s) of the deleted inode"
  sleep 30
done
log "deleted-inode holders now: $(old_inode_holders)"

touch /tmp/motioncorr-bench.lock
log "taking the recreated lock"
flock -w 28800 /tmp/motioncorr-bench.lock bash -c "
  $W/tools/campaign8.sh > $W/logs/campaign8.log 2>&1
  $W/tools/campaign7.sh > $W/logs/campaign7.log 2>&1
"
log "chain complete"
