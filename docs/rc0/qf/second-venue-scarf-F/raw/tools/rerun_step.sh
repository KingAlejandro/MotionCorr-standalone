#!/bin/bash
# One evidence-only rerun of ProfilingKit per configuration (runbook item 1/2/3 rerun form), with
# TMPDIR on node-local XFS instead of the PanFS /scratch path the login profile exports.
source /home/vol05/scarf1415/mc-rc0-scarfF/tools/env.sh
cd $QF_W
mkdir -p /tmp/wscarf-tmp && export TMPDIR=/tmp/wscarf-tmp
echo "rerun TMPDIR=$TMPDIR $(df -hT $TMPDIR | tail -1)" >> ctest-rerun-chain.out
for c in cpu cuda nvcomp; do
  cp ctest-$c.grade.json ctest-$c.grade.main.json
  bash tools/run_ctest.sh $c rerun '^ProfilingKit$'; echo "run_ctest $c rerun rc=$? exit=$(cat ctest-$c-rerun.exit 2>/dev/null)" >> ctest-rerun-chain.out
  python3 tools/grade_ctest.py $c --rerun-tag rerun > ctest-$c.grade-with-rerun.out 2>&1; echo "grade $c --rerun-tag rerun rc=$?" >> ctest-rerun-chain.out
  cat ctest-$c.grade-with-rerun.out >> ctest-rerun-chain.out
done
echo "end src HEAD $(git -C src rev-parse HEAD) porcelain=$(git -C src status --porcelain | wc -l)" >> ctest-rerun-chain.out
rm -rf /tmp/wscarf-tmp
echo RERUN_STEP_DONE > rerun.sentinel
