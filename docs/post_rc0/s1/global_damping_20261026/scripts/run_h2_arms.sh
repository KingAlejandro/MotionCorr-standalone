#!/bin/bash
# usage: run_h2_arms.sh   (on cpu64) H2 arms on the #267 eight cases, same lane/driver/evaluator as run_arms.sh.
#  h2-flagsoff       H2 binary, flags off, unchanged C1 driver (prediction 1 on the new binary)
#  h2all-prod        --experimental_coupled_peak all                (max_iter 5, tolerance 0.5)
#  h2glob-prod       --experimental_coupled_peak global
#  h2all-long        all    + --max_iter 50 --experimental_align_tolerance 1e-9
#  h2glob-long       global + --max_iter 50 --experimental_align_tolerance 1e-9
# Matched controls are the earlier arms a-cand-flagsoff (flags off) and d-gain1-long (long budget, gain 1); not rerun.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-h2; V=$DS_SC/v2; R=$V/receipts-h2; mkdir -p $R
BIN=$DS_SC/build-h2/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "h2 $DS_CAND_SHA"; sha256sum $BIN; lane grep Cpus_allowed_list /proc/self/status
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $R/env.txt 2>&1
run_arm() { # name extra
  local n=$1 extra=$2 drv=$D/ds_run_v2_cases.py
  [ -z "$extra" ] && drv=$D/c1_run_v2_cases.py
  if [ -z "$extra" ]; then lane $DS_PY -I $drv $V $n cpu $BIN unset $DS_CPUS > $R/$n.driver.out 2>&1; else lane $DS_PY -I $drv $V $n cpu $BIN unset $DS_CPUS "$extra" > $R/$n.driver.out 2>&1; fi
  echo $? > $R/$n.driver.exit
  lane $DS_PY -I $S/docs/post_rc0/s1/synth_combined/eval_v2.py $V/v2fixtures $V/$n $V/$n.eval.json > $R/$n.eval.out 2>&1
  echo $? > $R/$n.eval.exit
  echo "$n driver=$(cat $R/$n.driver.exit) eval=$(cat $R/$n.eval.exit)"
}
LONG="--max_iter 50 --experimental_align_tolerance 1e-9"
run_arm h2-flagsoff ""
run_arm h2all-prod  "--experimental_coupled_peak all"
run_arm h2glob-prod "--experimental_coupled_peak global"
run_arm h2all-long  "--experimental_coupled_peak all $LONG"
run_arm h2glob-long "--experimental_coupled_peak global $LONG"
