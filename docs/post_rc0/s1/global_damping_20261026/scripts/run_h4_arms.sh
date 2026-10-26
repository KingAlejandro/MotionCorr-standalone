#!/bin/bash
# usage: run_h4_arms.sh   (on cpu64) Reruns, with the #269 runtime capture, of the five arms needed to score the runtime field:
#   a-rt          hook binary ARM=none, flags off                  (same computation as arm a)
#   dcg-prod-rt / dcg-long-rt          ARM=global
#   dcgh2g-prod-rt / dcgh2g-long-rt    ARM=global + --experimental_coupled_peak global
# The driver's 'dc' argument is 'cap' (any value other than 'unset') so MC_DIAG_MODEL_OUT=<out>/<case>.runtime.json is set per case.
# Then: STAR of every rerun case must be byte-identical to the corresponding earlier STAR-only arm (capture changes no product),
# and the runtime field is scored by eval_runtime_v2.py (same truth, ROI, limits).
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-h4; V=$DS_SC/v2; R=$V/receipts-h4; mkdir -p $R
BIN=$DS_SC/build-h4on/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "h4 $DS_CAND_SHA"; sha256sum $BIN; lane grep Cpus_allowed_list /proc/self/status
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $R/env.txt 2>&1
LONG="--max_iter 50 --experimental_align_tolerance 1e-9"
run_arm() { # name dcarm extra old_arm
  local n=$1 dc=$2 extra=$3 old=$4 drv=$D/ds_run_v2_cases.py
  [ -z "$extra" ] && drv=$D/c1_run_v2_cases.py
  if [ -z "$extra" ]; then lane env MC_EXPERIMENT_CCF_DC_ARM=$dc $DS_PY -I $drv $V $n cpu $BIN cap $DS_CPUS > $R/$n.driver.out 2>&1
  else lane env MC_EXPERIMENT_CCF_DC_ARM=$dc $DS_PY -I $drv $V $n cpu $BIN cap $DS_CPUS "$extra" > $R/$n.driver.out 2>&1; fi
  echo $? > $R/$n.driver.exit
  lane $DS_PY -I $S/docs/post_rc0/s1/synth_combined/eval_v2.py $V/v2fixtures $V/$n $V/$n.eval.json > $R/$n.eval.out 2>&1; echo $? > $R/$n.eval.exit
  lane env MOTIONCORR_SRC=$S $DS_PY -I $D/eval_runtime_v2.py $V/v2fixtures $V/$n $V/$n.eval.json $V/$n.runtime-eval.json > $R/$n.runtime-eval.out 2>&1; echo $? > $R/$n.runtime-eval.exit
  nd=0; for c in zero integer fractional affine pedestal noisy flat repeated; do cmp -s $V/$n/$c/$c.star $V/$old/$c/$c.star || { nd=$((nd+1)); echo "STAR differs: $n/$c vs $old" >> $R/$n.star-identity.txt; }; done
  echo "$nd" > $R/$n.star-differing-cases
  echo "$n dc=$dc driver=$(cat $R/$n.driver.exit) eval=$(cat $R/$n.eval.exit) runtime-eval=$(cat $R/$n.runtime-eval.exit) star-differing-cases=$nd"
}
run_arm a-rt             none   ""                                                   a-cand-flagsoff
run_arm dcg-prod-rt      global ""                                                   dcg-prod
run_arm dcg-long-rt      global "$LONG"                                              dcg-long
run_arm dcgh2g-prod-rt   global "--experimental_coupled_peak global"                 dcgh2g-prod
run_arm dcgh2g-long-rt   global "--experimental_coupled_peak global $LONG"           dcgh2g-long
