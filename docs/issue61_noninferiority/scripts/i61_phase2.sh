#!/bin/bash
# Issue 61: control-arm jackknife reconstructions, then post-processing of everything.
# Review findings 4111302903 (consumed a job file it never generated) and 4111302927/8 applied
# here too: both completion markers are conditional on exit status and output count, and an
# empty job list is not a completed batch.
set -u
ROOT=${ROOT:-/home/alex/mc-issue61}
PY=${PY:-/home/alex/relion-container-tests/venvs/pipeliner-onedep-adapter/bin/python}
NPAR=${NPAR:-8}
{
  echo "PHASE2_LOCK $(date -u +%FT%TZ)"
  "$PY" "$ROOT/scripts/i61_ctrl_jk.py" || { echo "PHASE2_FAILED: could not generate control jobs"; exit 1; }

  EXP_REC=$(grep -c . "$ROOT/jobs_reconstruct_ctrl.txt")
  [ "$EXP_REC" -gt 0 ] || { echo "PHASE2_FAILED: empty control job list"; exit 1; }
  nice -n 5 xargs -P "$NPAR" -I{} -d '\n' bash -c '{}' < "$ROOT/jobs_reconstruct_ctrl.txt"
  rc=$?
  n=$(ls "$ROOT"/rec/*/*.mrc 2>/dev/null | wc -l)
  if [ "$rc" -ne 0 ]; then
    echo "CTRL_JK_FAILED $(date -u +%FT%TZ) xargs_rc=$rc maps=$n"; exit 1
  fi
  echo "CTRL_JK_DONE $(date -u +%FT%TZ) maps=$n"

  "$PY" "$ROOT/scripts/i61_stageB_pp.py" || { echo "PHASE2_FAILED: could not plan post-processing"; exit 1; }
  EXP_PP=$(grep -c . "$ROOT/jobs_postprocess.txt")
  [ "$EXP_PP" -gt 0 ] || { echo "PHASE2_FAILED: empty post-processing job list"; exit 1; }
  nice -n 5 xargs -P "$NPAR" -I{} -d '\n' bash -c '{}' < "$ROOT/jobs_postprocess.txt"
  rc=$?
  pp=$(ls "$ROOT"/pp/*/*.star 2>/dev/null | wc -l)
  errs=$(cat "$ROOT"/logs/pp_*.log 2>/dev/null | grep "ERROR" | grep -cv "ERROR in executing: gs " || true)
  if [ "$rc" -eq 0 ] && [ "$pp" -ge "$EXP_PP" ] && [ "$errs" -eq 0 ]; then
    echo "POSTPROCESS_DONE $(date -u +%FT%TZ) pp=$pp/$EXP_PP"
  else
    echo "POSTPROCESS_FAILED $(date -u +%FT%TZ) xargs_rc=$rc pp=$pp/$EXP_PP non_ghostscript_ERROR_lines=$errs"
    exit 1
  fi
} > "$ROOT/logs/phase2_driver.log" 2>&1
