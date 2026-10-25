#!/bin/bash
# Sequential chain on cpu64; each stage logs its exit; the chain stops at the first lane failure (exit 1 = lock contended).
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
for st in run_arms flagsoff ctest_cpu mutants; do
  bash $D/$st.sh > $DS_SC/chain-$st.out 2>&1; rc=$?; echo "$st exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain.log
  [ $rc -eq 0 ] || [ $st = ctest_cpu ] || { echo "stopping after $st"; exit 1; }
done
