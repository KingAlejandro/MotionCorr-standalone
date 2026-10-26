#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
step() { bash $D/$1.sh > $DS_SC/chain-h4-$2.out 2>&1; rc=$?; echo "$2 exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-h4.log; }
step build_h4 build
DS_ARM=h4off DS_SRC=h4 step ctest_cpu ctest-h4off
MC_EXPERIMENT_CCF_DC_ARM=none DS_ARM=h4on DS_SRC=h4 step ctest_cpu ctest-h4on
step run_h4_arms arms
step run_noisy_diag diag
step flagsoff_h4 flagsoff
