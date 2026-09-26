#!/bin/bash
ROOT=/home/alex/mc-issue61
{
  echo "LOCK_ACQUIRED $(date -u +%FT%TZ)"
  echo "affinity: $(taskset -cp $$ 2>/dev/null)"
  nice -n 5 xargs -P 8 -I{} -d '\n' bash -c '{}' < $ROOT/jobs_reconstruct.txt
  echo "RECONSTRUCT_DONE $(date -u +%FT%TZ) maps=$(ls $ROOT/rec/*/*.mrc 2>/dev/null|wc -l)"
} > $ROOT/logs/reconstruct_driver.log 2>&1
