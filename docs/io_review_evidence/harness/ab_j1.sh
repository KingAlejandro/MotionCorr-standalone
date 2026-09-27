#!/bin/bash
# 24-movie same-backend A/B, main vs PR #90 head, CPU backend, --j 1.
#
# Re-run. The first pass produced the same numbers (see
# ab-j1-firstpass-oldcomparator.log) but its driver removed the output trees on
# exit, so the JSON could not be re-graded with the updated comparator and was
# overwritten by a grade of an empty directory. The trees are kept this time.
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-io-evidence
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
echo "=== provenance ==="; date -Is; hostname; uptime
grep Cpus_allowed_list /proc/self/status
md5sum $R/harness/compare_outputs.py
sha256sum $R/src-main/build-cpu/motioncorr $R/src-pr90/build-cpu/motioncorr
for s in main pr90; do
  echo "--- src-$s ---"
  git -C $R/src-$s rev-parse HEAD
  git -C $R/src-$s status --porcelain | wc -l
done

rm -rf $R/ab-j1
taskset -c 40-46 python3 $R/harness/compare_outputs.py --repo $R/src-pr90 \
  --ref-binary $R/src-main/build-cpu/motioncorr --ref-label main \
  --test-binary $R/src-pr90/build-cpu/motioncorr --test-label pr90 \
  --tutorial $HOME/mc51/tutorial --threads 1 \
  --work $R/ab-j1 --json $R/evidence/pr90_outputs_j1.json
echo "ab j1 exit=$?"
echo "=== AB J1 RERUN DONE ==="; date -Is
