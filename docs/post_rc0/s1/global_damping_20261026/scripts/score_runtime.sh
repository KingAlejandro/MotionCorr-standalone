#!/bin/bash
# usage: score_runtime.sh   (on cpu64) Re-score the runtime field of the five captured arms (no native rerun). Attempt 1 of run_h4_arms.sh
# failed in the scorer's source-root discovery (exit 1: scorer lives outside the source tree), so scoring was repeated with MOTIONCORR_SRC set.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
S=$DS_SC/src-h4; V=$DS_SC/v2; R=$V/receipts-h4
for n in a-rt dcg-prod-rt dcg-long-rt dcgh2g-prod-rt dcgh2g-long-rt; do
  lane env MOTIONCORR_SRC=$S $DS_PY -I $D/eval_runtime_v2.py $V/v2fixtures $V/$n $V/$n.eval.json $V/$n.runtime-eval.json > $R/$n.runtime-eval.out 2>&1; echo $? > $R/$n.runtime-eval.exit
  echo "$n runtime-eval=$(cat $R/$n.runtime-eval.exit)"
done
