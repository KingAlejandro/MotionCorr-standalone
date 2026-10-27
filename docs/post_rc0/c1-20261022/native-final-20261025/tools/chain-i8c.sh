#!/bin/bash
# i8c chain = item-12 multi-device follow-up (read-only regrade of the retained arms after the d4poison grader crash + the not-yet-run dpoison_both arm), then K269 attribution.
# K269 attribution (i8b), after chain-i8 finished: C1 CUDA census sums differ from the retained #269 CUDA census (reference source #254+#260 with an observation overlay)
# in 90/100 movies (STAR identical 100/100). Frozen expectations BEFORE running: (A) n254_260 (3d560a16) reproduces the retained sums exactly (sum_equal 50/50, STAR equal);
# (B) N21093 (adds #270) equals C1 exactly (50/50); (C) n254_260 differs from C1 in exactly the movies where retained differs from C1 (contrast025, dose05, outmodel, contrast4
# conditions differ in part; pedestal32 equal). Any other outcome leaves the K269 difference unattributed.
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-i8-20261025
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f PYTHONDONTWRITEBYTECODE=1
T=$SC/tools-v3c-run; source $T/c1_env.sh || exit 1
cd $SC
until [ -e logs/chain-i8.done ] || [ -e logs/chain-i8.stop ]; do sleep 20; done
awk '/Cpus_allowed_list/{print $2}' /proc/self/status > logs/chain-i8c.cpus
echo $$ > logs/chain-i8c.pid; date -u +%FT%TZ > logs/chain-i8c.started
[ "$(cat logs/chain-i8c.cpus)" = 96-103 ] || { echo "not pinned: $(cat logs/chain-i8c.cpus)" > logs/chain-i8c.stop; exit 1; }
S="bash $T/c1_stage.sh"
$S i8c-mg-item12-regrade bash $T/c1_mg.sh i8c-mg-item12-regrade $C1_PY $T/c1_item12_mg.py --dataset --regrade d1,d2,dshim,d4,dpoison,d4poison
$S i8c-mg-item12-both bash $T/c1_mg.sh i8c-mg-item12-both $C1_PY $T/c1_item12_mg.py --dataset --arms dpoison_both
CONDS="contrast025 dose05 outmodel contrast4 pedestal32"
$S i8b-build-n254_260 bash $T/c1_attr_build8.sh n254_260
$S i8b-build-N21093 bash $T/c1_attr_build8.sh N21093
for arm in n254_260 N21093; do
  $S i8b-census-$arm bash $T/c1_gpu_run.sh i8b-census-$arm taskset -c $C1_CPUS $C1_PY $T/c1_census_runner.py --root $SC/census --binary $SC/attr/$arm/build/motioncorr --backend cuda --cpus $C1_CPUS --dc-arms none --double-conditions --results results-$arm --conditions $CONDS --max-idle-seconds 600
done
cmp() { $S i8b-cmp-$1 taskset -c $C1_CPUS $C1_PY $T/c1_census.py compare results-$2 $3 $4 cuda $SC/i8b-cmp-$1.json; }
# compare(results, ref_root, ref_arm, backend, out): C1 results are the 'results' side only for subsets, so compare each subset against the reference tree
cmp n254_260-vs-retained n254_260 $C1_KM_CUDA_REF cuda-none
cmp N21093-vs-c1 N21093 $SC/census/results-c1-cuda cuda-none
cmp n254_260-vs-c1 n254_260 $SC/census/results-c1-cuda cuda-none
date -u +%FT%TZ > logs/chain-i8c.finished; echo chain-done > logs/chain-i8c.done
