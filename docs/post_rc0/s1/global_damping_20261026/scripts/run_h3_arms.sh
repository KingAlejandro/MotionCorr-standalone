#!/bin/bash
# usage: run_h3_arms.sh   (on cpu64) H3 arms on the #267 eight cases; hook binary build-h3on, same lane/driver/evaluator.
# Every run sets MC_EXPERIMENT_CCF_DC_ARM (required by the hook): 'global' for DC arms, 'none' for the DC-off identity arm.
#  h3-dcoff            hook binary, ARM=none, flags off, unchanged C1 driver  (DC-off identity vs a)
#  dcg-prod / dcg-long            ARM=global, separable peak, gain 1
#  dcgh2g-prod / dcgh2g-long      ARM=global + --experimental_coupled_peak global
#  dcghalf-prod / dcghalf-long    ARM=global + --experimental_global_half_gain
#  e-half-iter50-tol05            ARM=none, half gain, --max_iter 50, default tolerance (item 3: early-stop test; iteration
#                                 accounting comes from the [align] stdout line, no driver change)
# long = --max_iter 50 --experimental_align_tolerance 1e-9. Controls a, b, c, d, h2glob-* are reused, not rerun.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-h3; V=$DS_SC/v2; R=$V/receipts-h3; mkdir -p $R
BIN=$DS_SC/build-h3on/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "h3 $DS_CAND_SHA"; sha256sum $BIN; lane grep Cpus_allowed_list /proc/self/status
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $R/env.txt 2>&1
run_arm() { # name dcarm extra
  local n=$1 dc=$2 extra=$3 drv=$D/ds_run_v2_cases.py
  [ -z "$extra" ] && drv=$D/c1_run_v2_cases.py
  if [ -z "$extra" ]; then lane env MC_EXPERIMENT_CCF_DC_ARM=$dc $DS_PY -I $drv $V $n cpu $BIN unset $DS_CPUS > $R/$n.driver.out 2>&1
  else lane env MC_EXPERIMENT_CCF_DC_ARM=$dc $DS_PY -I $drv $V $n cpu $BIN unset $DS_CPUS "$extra" > $R/$n.driver.out 2>&1; fi
  echo $? > $R/$n.driver.exit
  lane $DS_PY -I $S/docs/post_rc0/s1/synth_combined/eval_v2.py $V/v2fixtures $V/$n $V/$n.eval.json > $R/$n.eval.out 2>&1
  echo $? > $R/$n.eval.exit
  echo "$n dc=$dc driver=$(cat $R/$n.driver.exit) eval=$(cat $R/$n.eval.exit)"
}
LONG="--max_iter 50 --experimental_align_tolerance 1e-9"
run_arm h3-dcoff           none   ""
run_arm dcg-prod           global ""
run_arm dcg-long           global "$LONG"
run_arm dcgh2g-prod        global "--experimental_coupled_peak global"
run_arm dcgh2g-long        global "--experimental_coupled_peak global $LONG"
run_arm dcghalf-prod       global "--experimental_global_half_gain"
run_arm dcghalf-long       global "--experimental_global_half_gain $LONG"
run_arm e-half-iter50-tol05 none  "--experimental_global_half_gain --max_iter 50"
