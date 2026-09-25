#!/bin/bash
# Issue 61: control-arm jackknife reconstructions, then post-processing of everything.
ROOT=/home/alex/mc-issue61
{
  echo "PHASE2_LOCK $(date -u +%FT%TZ)"
  nice -n 5 xargs -P 8 -I{} -d '\n' bash -c '{}' < $ROOT/jobs_reconstruct_ctrl.txt
  echo "CTRL_JK_DONE $(date -u +%FT%TZ) maps=$(ls $ROOT/rec/*/*.mrc|wc -l)"
  /home/alex/relion-container-tests/venvs/pipeliner-onedep-adapter/bin/python \
      $ROOT/scripts/i61_stageB_pp.py
  nice -n 5 xargs -P 8 -I{} -d '\n' bash -c '{}' < $ROOT/jobs_postprocess.txt
  echo "POSTPROCESS_DONE $(date -u +%FT%TZ) pp=$(ls $ROOT/pp/*/*.star 2>/dev/null|wc -l)"
} > $ROOT/logs/phase2_driver.log 2>&1
