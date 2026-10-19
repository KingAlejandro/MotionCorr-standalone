#!/bin/bash
# runs the unmodified QF run_ctest.sh + grade_ctest.py for cpu, cuda, nvcomp in order
source /home/vol05/scarf1415/mc-rc0-scarfF/tools/env.sh
cd $QF_W
bash tools/identity.sh > identity-ctest.txt 2>&1
for c in cpu cuda nvcomp; do
  bash tools/run_ctest.sh $c; echo "run_ctest $c rc=$? exit=$(cat ctest-$c.exit 2>/dev/null)" >> ctest-chain.out
  python3 tools/grade_ctest.py $c > ctest-$c.grade.out 2>&1; echo "grade $c rc=$?" >> ctest-chain.out
  cat ctest-$c.grade.out >> ctest-chain.out
done
nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader > compute-apps-after.txt 2>&1
echo "end src HEAD $(git -C src rev-parse HEAD) porcelain=$(git -C src status --porcelain | wc -l)" >> ctest-chain.out
echo CTEST_STEP_DONE > ctest.sentinel
