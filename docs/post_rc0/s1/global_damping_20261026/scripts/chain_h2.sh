#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
export DS_ARM=h2
for st in ctest_cpu mutants_h2 run_h2_arms flagsoff_h2; do
  bash $D/$st.sh > $DS_SC/chain-h2-$st.out 2>&1; rc=$?; echo "$st exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-h2.log
done
