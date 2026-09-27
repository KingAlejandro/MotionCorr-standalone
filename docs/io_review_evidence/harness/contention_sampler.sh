#!/bin/bash
# Records machine contention for the whole j4 + timing window. cpu64 is a
# shared box: two unpinned ctffind processes belonging to another worker have
# been resident for 47+ days, and a 64-core python job is also present. The
# timing leg cannot claim an idle machine, so it records what else was running
# instead of pretending the question does not arise.
out=$HOME/mc-io-evidence/evidence/contention-during-timing.log
: > $out
while :; do
  {
    echo "=== $(date -Is) ==="
    cat /proc/loadavg
    ps -eo user,pid,psr,pcpu,etime,comm --sort=-pcpu | head -12
  } >> $out
  sleep 30
done
