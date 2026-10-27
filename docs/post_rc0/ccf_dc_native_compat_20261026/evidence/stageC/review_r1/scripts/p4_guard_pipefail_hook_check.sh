#!/bin/bash
# P4: stageC_guard.sh line 19 uses `env | grep -q` under `set -o pipefail`. If grep exits on its first match while env is
# still writing, env dies of SIGPIPE, the pipeline status is 141 and the hook check reads as "absent". Expected rc 20
# (hook rejected); rc 15 means the check was passed and the guard went on to the next validation.
# Usage: p4.sh GUARD_PATH ; no command shims, no GPU, no /proc; the guard stops at its argument validation.
G=$1
big=$(head -c 300000 /dev/zero | tr '\0' x)
for mode in small big; do
  c20=0; c15=0; other=0
  for i in $(seq 1 20); do
    if [ $mode = big ]; then
      env -i PATH=/usr/bin:/bin STAGEC_TEST_NO_SLEEP=1 STAGEC_REAL=1 ZBIG=$big bash "$G" lbl 1 >/dev/null 2>&1; rc=$?
    else
      env -i PATH=/usr/bin:/bin STAGEC_TEST_NO_SLEEP=1 STAGEC_REAL=1 bash "$G" lbl 1 >/dev/null 2>&1; rc=$?
    fi
    case $rc in 20) c20=$((c20+1));; 15) c15=$((c15+1));; *) other=$((other+1));; esac
  done
  echo "$mode env: rc20(hook rejected)=$c20 rc15(hook check passed)=$c15 other=$other"
done
bash --version | head -1
