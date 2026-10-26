#!/bin/bash
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
step() { bash $D/$1.sh > $DS_SC/chain-h6-$2.out 2>&1; rc=$?; echo "$2 exit $rc $(date -u +%FT%TZ)" | tee -a $DS_SC/chain-h6.log; }
step run_h6_arms arms
step flagsoff_h6 flagsoff
