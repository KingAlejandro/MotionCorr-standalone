#!/bin/bash
# Driver: runs inside the flock, pins affinity, builds all three binaries.
set -uo pipefail
trap 'rm -f /tmp/motioncorr-gpu-timing.lock' EXIT
echo "mc3-compare builds (t3code-eb197c97) pid=$$ since $(date -u +%H:%M:%SZ)" > /tmp/motioncorr-gpu-timing.lock
cd /home/alex/mc3-compare
echo "### affinity=$(taskset -cp $$ 2>&1 | sed 's/.*: //')  nproc=$(nproc)  load=$(cat /proc/loadavg)"
for step in "setup_work.sh" "build_motioncorr.sh" "build_mc3.sh stock" "build_mc3.sh o3"; do
  echo; echo "################ $step  $(date -u +%H:%M:%SZ)"
  bash $step; rc=$?
  echo "################ $step exit=$rc"
  [ $rc -ne 0 ] && echo "ABORTING" && exit $rc
done
echo; echo "### ALL BUILDS DONE $(date -u +%H:%M:%SZ)"
