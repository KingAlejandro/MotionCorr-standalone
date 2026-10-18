#!/bin/bash
# Attended-run watcher (R-D11 r9 operator checklist). Logs only; termination is done by the operator.
E=/mnt/clathrin/alex-motioncorr-rc0/W-D11/confirm4; LOG=$E/operator-watch.log
seen=0; warned=""; last_holder=""
ev(){ echo "$(date -u +%FT%TZ) $*" >> $LOG; }
ev "watch start"
while true; do
  n=$(grep -c "^===" $E/campaign.out); if [ "$n" -gt "$seen" ]; then grep "^===" $E/campaign.out | tail -n +$((seen+1)) | while read -r l; do ev "LAUNCHER $l"; done; seen=$n; fi
  launcher=$(pgrep -f "confirm_4gpus.sh windows" | head -1)
  holder=$(awk '$6 ~ /:8658$/ {print $5}' /proc/locks | head -1)
  workers=$(pgrep -f "confirm_pairs.py worker" | tr "\n" " ")
  holders=$(pgrep -f "confirm_pairs.py run" | tr "\n" " ")
  if [ -n "$holder" ]; then
    et=$(ps -o etimes= -p $holder 2>/dev/null | tr -d " ")
    if [ "$holder" != "$last_holder" ]; then ev "LOCK holder=$holder workers=[$workers]"; last_holder=$holder; warned=""; fi
    if [ -n "$et" ] && [ "$et" -ge 2700 ]; then ev "OVERRUN holder=$holder etimes=$et lock still held"; fi
    if [ -n "$et" ] && [ "$et" -ge 2650 ] && [ -z "$warned" ]; then ev "WARN holder=$holder etimes=$et near ceiling"; warned=1; fi
  elif [ -n "$last_holder" ]; then ev "RELEASE lock free (last holder $last_holder)"; last_holder=""; fi
  if [ -z "$holders" ] && [ -n "$workers" ]; then ev "ORPHAN worker(s) [$workers] alive with no holder"; fi
  if [ -z "$launcher" ] && [ -z "$holders" ]; then ev "CAMPAIGN ENDED"; tail -n 5 $E/campaign.out | while read -r l; do ev "TAIL $l"; done; exit 0; fi
  sleep 15
done
