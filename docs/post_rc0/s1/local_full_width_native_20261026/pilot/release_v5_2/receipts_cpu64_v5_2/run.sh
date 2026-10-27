#!/bin/bash
# Read-only audit under lane.py: hashes of the produced noisy/OFF run, the r1 decision/run files, and both baseline trees (original scratch and durable).
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; O=$NS/diag-continuation-r2
echo "start $(date -u +%FT%TZ)"; uptime; taskset -pc $$
(cd $NS/evidence && find . -type f | sort | xargs sha256sum) > $O/inventory_evidence.sha256
(cd $NS/decision-native-r1 && find . -type f | sort | xargs sha256sum) > $O/inventory_decision_r1.sha256
(cd $NS/native-run-r1 && find . -type f | sort | xargs sha256sum) > $O/inventory_native_run_r1.sha256
for root in /tmp/motioncorr-b2-factorial-20261026/evidence/runs /home/ubuntu/motioncorr-evidence/native-b2-upstream-factorial-20261026/task/evidence/runs; do
  tag=$(echo $root | grep -q home && echo durable || echo original)
  for c in noisy affine pedestal zero integer fractional flat repeated; do (cd $root/$c/UP_only && find . -type f -printf "%s " -exec sha256sum {} \; | sed "s#^#$c #" ) ; done > $O/baseline_$tag.txt
done
find /tmp/motioncorr-b2-factorial-20261026/evidence/runs /home/ubuntu/motioncorr-evidence/native-b2-upstream-factorial-20261026/task/evidence/runs -type l | wc -l > $O/symlinks_in_baselines.txt
echo "end $(date -u +%FT%TZ)"
