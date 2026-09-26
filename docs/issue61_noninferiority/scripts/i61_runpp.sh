#!/bin/bash
ROOT=/home/alex/mc-issue61
{
  echo "PP_LOCK $(date -u +%FT%TZ)"
  nice -n 5 xargs -P 8 -I{} -d '\n' bash -c '{}' < $ROOT/jobs_postprocess.txt
  echo "POSTPROCESS_DONE $(date -u +%FT%TZ) n=$(ls $ROOT/pp/*/*.star 2>/dev/null|wc -l)"
} > $ROOT/logs/postprocess_driver.log 2>&1
