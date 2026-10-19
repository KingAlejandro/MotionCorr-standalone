#!/bin/bash
# usage: cmp.sh <fam> <runA> <runB> [more compare args]
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
fam=$1; a=$2; b=$3; shift 3
mkdir -p $S/cmp
taskset -c 80-87 /home/alex/mc-env/bin/python3 $S/src-branch/docs/issue85_laneC/compare_output_trees.py $S/runs/$a $S/runs/$b --manifest $S/inputs/manifest_$fam.json --json-out $S/cmp/${a}__${b}.json "$@" 2>&1 | tail -4
echo "cmp-rc=${PIPESTATUS[0]}"
