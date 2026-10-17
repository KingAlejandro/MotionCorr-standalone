#!/bin/bash
# Issue 61 Stage B reconstruction driver.
# Review findings 4111302938/4111302927: the original discarded the xargs exit status and
# emitted its completion marker unconditionally, so a partial batch was indistinguishable
# from a complete one downstream.  The marker is now conditional on BOTH a clean xargs
# status AND the expected output count.
set -u
ROOT=${ROOT:-/home/alex/mc-issue61}
{
  echo "LOCK_ACQUIRED $(date -u +%FT%TZ)"
  echo "affinity: $(taskset -cp $$ 2>/dev/null)"
  EXPECTED=$(grep -c . "$ROOT/jobs_reconstruct.txt")
  nice -n 5 xargs -P "${NPAR:-8}" -I{} -d '\n' bash -c '{}' < "$ROOT/jobs_reconstruct.txt"
  rc=$?
  n=$(ls "$ROOT"/rec/*/*.mrc 2>/dev/null | wc -l)
  errs=$(grep -l ERROR "$ROOT"/logs/rec_*.log 2>/dev/null | wc -l)
  # an empty job list is not a completed batch
  if [ "${EXPECTED:-0}" -gt 0 ] && [ "$rc" -eq 0 ] && [ "$n" -ge "$EXPECTED" ] && [ "$errs" -eq 0 ]; then
    echo "RECONSTRUCT_DONE $(date -u +%FT%TZ) maps=$n/$EXPECTED"
  else
    echo "RECONSTRUCT_FAILED $(date -u +%FT%TZ) xargs_rc=$rc maps=$n/$EXPECTED logs_with_ERROR=$errs"
    exit 1
  fi
} > "$ROOT/logs/reconstruct_driver.log" 2>&1
