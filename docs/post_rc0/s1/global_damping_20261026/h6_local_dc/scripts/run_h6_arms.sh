#!/bin/bash
# usage: run_h6_arms.sh   (on cpu64) H6 arms on the #267 eight cases, hook binary build-h5on (source 20e52f57, identical to the previous round's binary).
#  dcbh2a-prod / -long   MC_EXPERIMENT_CCF_DC_ARM=both,   --experimental_coupled_peak all
#  dcbh2g-prod / -long   MC_EXPERIMENT_CCF_DC_ARM=both,   --experimental_coupled_peak global
#  dcgh2a-prod / -long   MC_EXPERIMENT_CCF_DC_ARM=global, --experimental_coupled_peak all
# long = --max_iter 50 --experimental_align_tolerance 1e-9. Control DCg+H2g (dcgh2g-*-rt) is reused, not rerun. No new flags.
# Runtime capture on (MC_DIAG_MODEL_OUT via the driver's dc argument 'cap'); STAR by eval_v2, runtime by eval_runtime_v2.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-h5; V=$DS_SC/v2; R=$V/receipts-h6; mkdir -p $R
BIN=$DS_SC/build-h5on/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "h6 binary source $DS_CAND_SHA"; sha256sum $BIN; lane grep Cpus_allowed_list /proc/self/status
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $R/env.txt 2>&1
run_arm() { # name dcarm extra
  local n=$1 dc=$2 extra=$3
  lane env MC_EXPERIMENT_CCF_DC_ARM=$dc $DS_PY -I $D/ds_run_v2_cases.py $V $n cpu $BIN cap $DS_CPUS "$extra" > $R/$n.driver.out 2>&1; echo $? > $R/$n.driver.exit
  lane $DS_PY -I $S/docs/post_rc0/s1/synth_combined/eval_v2.py $V/v2fixtures $V/$n $V/$n.eval.json > $R/$n.eval.out 2>&1; echo $? > $R/$n.eval.exit
  lane env MOTIONCORR_SRC=$S $DS_PY -I $D/eval_runtime_v2.py $V/v2fixtures $V/$n $V/$n.eval.json $V/$n.runtime-eval.json > $R/$n.runtime-eval.out 2>&1; echo $? > $R/$n.runtime-eval.exit
  echo "$n dc=$dc driver=$(cat $R/$n.driver.exit) eval=$(cat $R/$n.eval.exit) runtime-eval=$(cat $R/$n.runtime-eval.exit)"
}
LONG="--max_iter 50 --experimental_align_tolerance 1e-9"
run_arm dcbh2a-prod both   "--experimental_coupled_peak all"
run_arm dcbh2g-prod both   "--experimental_coupled_peak global"
run_arm dcgh2a-prod global "--experimental_coupled_peak all"
run_arm dcbh2a-long both   "--experimental_coupled_peak all $LONG"
run_arm dcbh2g-long both   "--experimental_coupled_peak global $LONG"
run_arm dcgh2a-long global "--experimental_coupled_peak all $LONG"
