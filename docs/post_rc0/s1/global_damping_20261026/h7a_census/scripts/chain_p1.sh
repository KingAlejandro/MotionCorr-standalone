#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
step() { bash $D/$1.sh > $DS_SC/chain-p1x-$2.out 2>&1; rc=$?; echo "$2 exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-p1x.log; }
step build_p1 build
DS_ARM=p1off DS_SRC=p1 step ctest_cpu ctest-p1off
MC_EXPERIMENT_CCF_DC_ARM=none DS_ARM=p1on DS_SRC=p1 step ctest_cpu ctest-p1on
step mutants_p1 mutants
step flagsoff_p1 flagsoff
