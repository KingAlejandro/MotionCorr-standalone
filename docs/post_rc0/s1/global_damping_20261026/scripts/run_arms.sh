#!/bin/bash
# usage: run_arms.sh   (on cpu64, env DS_SC DS_CAND_SHA DS_BASE_SHA set)
# #267 eight known-motion cases on the CPU build, arms a0/a/b/c/d, then the unchanged #267 evaluator on each.
#  a0  base binary (e77a51a2), flags off, unchanged C1 driver     (same-host control for a)
#  a   cand binary,            flags off, unchanged C1 driver
#  b   cand, --experimental_global_half_gain                       (production stop: max_iter 5, tolerance 0.5)
#  c   cand, half gain + --max_iter 50 --experimental_align_tolerance 1e-9
#  d   cand, gain 1    + --max_iter 50 --experimental_align_tolerance 1e-9   (matched budget control for c)
# Each arm runs inside the lane: nonblocking flock, taskset CPUs 48-55. A contended lock stops the script; no retry.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-cand; V=$DS_SC/v2; mkdir -p $V; R=$V/receipts; mkdir -p $R
BASE_BIN=$DS_SC/build-base/motioncorr; CAND_BIN=$DS_SC/build-cand/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "base $DS_BASE_SHA"; echo "cand $DS_CAND_SHA"
  sha256sum $BASE_BIN $CAND_BIN; lane grep Cpus_allowed_list /proc/self/status; echo "lane rc=$?"
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $R/env.txt 2>&1
# no -I here: the generator imports its sibling module, exactly as the C1 c1_v2.sh runs it
[ -d $V/v2fixtures ] || lane $DS_PY $S/test-data/generate_motion_diagnostics.py --outdir $V/v2fixtures > $V/generate.log 2>&1 || { echo "fixture generation failed"; exit 2; }
( cd $V/v2fixtures && sha256sum $(find . -type f | sort) ) > $R/fixtures.sha256
run_arm() { # name binary extra
  local n=$1 bin=$2 extra=$3 drv=$D/ds_run_v2_cases.py
  [ -z "$extra" ] && drv=$D/c1_run_v2_cases.py
  if [ -z "$extra" ]; then lane $DS_PY -I $drv $V $n cpu $bin unset $DS_CPUS > $R/$n.driver.out 2>&1; else lane $DS_PY -I $drv $V $n cpu $bin unset $DS_CPUS "$extra" > $R/$n.driver.out 2>&1; fi
  echo $? > $R/$n.driver.exit
  lane $DS_PY -I $S/docs/post_rc0/s1/synth_combined/eval_v2.py $V/v2fixtures $V/$n $V/$n.eval.json > $R/$n.eval.out 2>&1
  echo $? > $R/$n.eval.exit
  echo "$n driver=$(cat $R/$n.driver.exit) eval=$(cat $R/$n.eval.exit)"
}
run_arm a0-base-flagsoff $BASE_BIN ""
run_arm a-cand-flagsoff  $CAND_BIN ""
run_arm b-half-prod      $CAND_BIN "--experimental_global_half_gain"
run_arm c-half-long      $CAND_BIN "--experimental_global_half_gain --max_iter 50 --experimental_align_tolerance 1e-9"
run_arm d-gain1-long     $CAND_BIN "--max_iter 50 --experimental_align_tolerance 1e-9"
