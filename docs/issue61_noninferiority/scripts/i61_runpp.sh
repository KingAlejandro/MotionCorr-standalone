#!/bin/bash
# Issue 61 Stage B post-processing driver.  See i61_runrec.sh: the completion marker is
# conditional on the xargs status and the expected output count (review finding 4111302927).
# Ghostscript logfile.pdf races between concurrent jobs in a shared output directory are
# tolerated explicitly, because they touch no numerical output.
set -u
ROOT=${ROOT:-/home/alex/mc-issue61}
{
  echo "PP_LOCK $(date -u +%FT%TZ)"
  EXPECTED=$(grep -c . "$ROOT/jobs_postprocess.txt")
  nice -n 5 xargs -P "${NPAR:-8}" -I{} -d '\n' bash -c '{}' < "$ROOT/jobs_postprocess.txt"
  rc=$?
  n=$(ls "$ROOT"/pp/*/*.star 2>/dev/null | wc -l)
  # per-LINE filter: a log containing both a ghostscript race and a real RELION ERROR must
  # still fail.  Exempting the whole file (earlier version) let a genuine error through.
  errs=$(cat "$ROOT"/logs/pp_*.log 2>/dev/null | grep "ERROR" \
         | grep -cv "ERROR in executing: gs " || true)
  if [ "${EXPECTED:-0}" -gt 0 ] && [ "$rc" -eq 0 ] && [ "$n" -ge "$EXPECTED" ] && [ "$errs" -eq 0 ]; then
    echo "POSTPROCESS_DONE $(date -u +%FT%TZ) pp=$n/$EXPECTED"
  else
    echo "POSTPROCESS_FAILED $(date -u +%FT%TZ) xargs_rc=$rc pp=$n/$EXPECTED non_ghostscript_ERROR_lines=$errs"
    exit 1
  fi
} > "$ROOT/logs/postprocess_driver.log" 2>&1
