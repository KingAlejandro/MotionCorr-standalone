#!/bin/bash
# Full CTest of one configuration (no exclusions), lane GPU3/CPUs 8-9. usage: c1_ctest.sh cpu|cuda|nvcomp
# Derived from docs/rc0/qf/tools/run_ctest.sh: no wait on the bench lock (policy #198: correctness does not wait; the probe is only recorded),
# numeric threads 1, nonblocking GPU lock held for the batch, foreign GPU process => stop (no waiting loop).
# Health: a failed pre-check stops the run (exit 3); a failed post-check makes the wrapper exit 37 even when CTest passed.
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
cfg=$1; B=$C1_SCR/build-$cfg; O=$C1_SCR/ctest-$cfg
cd "$C1_SCR/src" || exit 90
[ "$(git rev-parse HEAD)" = "$C1_SHA" ] && [ -z "$(git status --porcelain)" ] || { echo "source not exact/clean"; exit 92; }
if [ "$cfg" != cpu ]; then
  export CUDA_VISIBLE_DEVICES=$C1_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
  exec 9>"$C1_GPU_LOCK"; flock -n 9 || { echo "GPU3 correctness lock contended; stopping"; exit 5; }
  "$D/c1_occupancy.sh" "ctest-$cfg-pre"; pre=$?; echo $pre > $O.health-pre.exit
  [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
fi
{
  echo "start $(date -u +%FT%TZ) cfg=$cfg HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l)"
  echo "mask: $C1_CPUS gpu: ${CUDA_VISIBLE_DEVICES:-none}; bench lock probe: $(flock -n /tmp/motioncorr-bench.lock true && echo free || echo held)"
  echo "binary sha256: $(sha256sum $B/motioncorr | cut -c1-64)"
  ctest --test-dir $B -N | tail -3
  taskset -c $C1_CPUS $C1_PY tools/validate_test_collection.py --test-dir $B $([ $cfg != cpu ] && echo --cuda); echo "validate_test_collection rc=$?"
  if [ "$cfg" = cpu ]; then taskset -c $C1_CPUS $C1_PY tools/test_ci_fail_closed.py -v; echo "test_ci_fail_closed rc=$?"; fi
  taskset -c $C1_CPUS ctest --test-dir $B --output-on-failure -j1 --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"
  echo $rc > $O.exit
} > $O.log 2>&1
rc=$(cat $O.exit 2>/dev/null || echo 99)
if [ "$cfg" != cpu ]; then
  "$D/c1_occupancy.sh" "ctest-$cfg-post"; post=$?; echo $post > $O.health-post.exit
  if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (ctest rc=$rc)" | tee -a $O.log >&2; [ $rc -eq 0 ] && rc=37; fi
fi
exit $rc
