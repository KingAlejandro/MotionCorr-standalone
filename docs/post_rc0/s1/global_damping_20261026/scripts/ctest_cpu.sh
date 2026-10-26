#!/bin/bash
# usage: ctest_cpu.sh   (on cpu64) Full CPU CTest of the candidate Release build, no exclusions, inside the lane.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
A=${DS_ARM:-cand}; B=$DS_SC/build-$A; O=$DS_SC/ctest-$A; S=$DS_SC/src-$A
{
  echo "start $(date -u +%FT%TZ) cand=$DS_CAND_SHA binary=$(sha256sum $B/motioncorr | cut -c1-64)"
  ctest --test-dir $B -N | tail -3
  lane $DS_PY $S/tools/validate_test_collection.py --test-dir $B; echo "validate_test_collection rc=$?"
  (cd $S && lane $DS_PY $S/tools/test_ci_fail_closed.py -v); echo "test_ci_fail_closed rc=$?"
  lane ctest --test-dir $B --output-on-failure -j4 --output-junit $O.junit.xml; rc=$?
  echo "ctest rc=$rc end $(date -u +%FT%TZ)"
  echo $rc > $O.exit
} > $O.log 2>&1
exit $(cat $O.exit 2>/dev/null || echo 99)
