#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Full CTest of one candidate configuration, no exclusions (adapted from C1 c1_ctest.sh / QF run_ctest.sh).
# CPUs 14-15, numeric threads 1, bench lock only probed (#198), GPU1 lock nonblocking and held through post-health.
# usage: ctest.sh cpu|cuda|nvcomp ; exit 3 pre-health fail, 37 post-health fail after a passing CTest.
set -u
D=$(dirname "$0"); source "$D/lane.sh" || exit 1
cfg=$1; B=$G_SCR/build-cand-$cfg; O=$G_SCR/ctest-cand-$cfg
cd "$G_SCR/src-cand" || exit 90
[ "$(git rev-parse HEAD)" = "$G_SHA" ] && [ -z "$(git status --porcelain)" ] || { echo "source not exact/clean"; exit 92; }
if [ "$cfg" != cpu ]; then
  export CUDA_VISIBLE_DEVICES=$G_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
  exec 9>"$G_GPU_LOCK"; flock -n 9 || { echo "GPU1 correctness lock contended; stopping"; exit 5; }
  "$D/health.sh" "ctest-$cfg-pre" || { echo "pre-run health failed"; exit 3; }
fi
{
  echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l)"
  echo "mask: $G_CPUS gpu: ${CUDA_VISIBLE_DEVICES:-none}; bench lock probe: $(flock -n /tmp/motioncorr-bench.lock true && echo free || echo held)"
  echo "binary sha256: $(sha256sum $B/motioncorr | cut -c1-64)"
  ctest --test-dir $B -N | tail -3
  ctest --test-dir $B -N | grep -E 'LocalMotion(DistortionGuard|GuardModel|GuardCall)$'
  taskset -c $G_CPUS $G_PY tools/validate_test_collection.py --test-dir $B $([ $cfg != cpu ] && echo --cuda); echo "validate_test_collection rc=$?"
  if [ "$cfg" = cpu ]; then taskset -c $G_CPUS $G_PY tools/test_ci_fail_closed.py -v; echo "test_ci_fail_closed rc=$?"; fi
  taskset -c $G_CPUS ctest --test-dir $B --output-on-failure -j1 --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"
  echo $rc > $O.exit
} > $O.log 2>&1
rc=$(cat $O.exit 2>/dev/null || echo 99)
grep -q "validate_test_collection rc=0" $O.log || { echo "collection validation failed"; [ $rc -eq 0 ] && rc=36; }
if [ "$cfg" = cpu ]; then grep -q "test_ci_fail_closed rc=0" $O.log || { echo "fail-closed control failed"; [ $rc -eq 0 ] && rc=35; }; fi
if [ "$cfg" != cpu ]; then
  "$D/health.sh" "ctest-$cfg-post" || { echo "post-run health failed (ctest rc=$rc)"; [ $rc -eq 0 ] && rc=37; }
fi
exit $rc
