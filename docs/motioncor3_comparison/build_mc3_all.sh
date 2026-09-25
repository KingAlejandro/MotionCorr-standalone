#!/bin/bash
# Driver for the two MotionCor3 builds. Runs inside the flock.
# Deliberately does NOT write /tmp/motioncorr-gpu-timing.lock: that file is a single
# shared line with no ownership discipline, so concurrent writers make it lie. The
# flock is the only truth.
set -uo pipefail
cd /home/alex/mc3-compare
echo "### acquired $(date -u +%H:%M:%SZ) affinity=$(taskset -cp $$ 2>&1 | sed 's/.*: //') nproc=$(nproc) load=$(cat /proc/loadavg)"
for v in stock o3; do
  echo; echo "################ build_mc3.sh $v  $(date -u +%H:%M:%SZ)"
  bash build_mc3.sh $v; rc=$?
  echo "################ build_mc3.sh $v exit=$rc"
  [ $rc -ne 0 ] && echo "ABORTING" && exit $rc
done
echo; echo "### MOTIONCOR3 BUILDS DONE $(date -u +%H:%M:%SZ)"
