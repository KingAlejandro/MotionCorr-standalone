#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
step() { bash $D/$1.sh > $DS_SC/chain-h5-$2.out 2>&1; rc=$?; echo "$2 exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-h5.log; }
step build_h5 build
DS_ARM=h5off DS_SRC=h5 step ctest_cpu ctest-h5off
MC_EXPERIMENT_CCF_DC_ARM=none DS_ARM=h5on DS_SRC=h5 step ctest_cpu ctest-h5on
step mutants_h5 mutants
step run_nc_all nc
step flagsoff_h5 flagsoff
