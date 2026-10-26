#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
step() { bash $D/$1.sh > $DS_SC/chain-h3-$2.out 2>&1; rc=$?; echo "$2 exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-h3.log; }
step build_h3 build
# full CTest: default build (primary identity), then the hook build with the arm set to none
DS_ARM=h3off DS_SRC=h3 step ctest_cpu ctest-h3off
MC_EXPERIMENT_CCF_DC_ARM=none DS_ARM=h3on DS_SRC=h3 step ctest_cpu ctest-h3on
step mutants_h3 mutants
step run_h3_arms arms
step flagsoff_h3 flagsoff
