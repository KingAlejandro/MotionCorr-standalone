#!/bin/bash
# strict complete non-PDF tree comparison (logs included), plus products-only. Declared log allowances:
#   route lines from #195 (pre-#197 arm only differs there), the injected-fallback WARNING/CUDA Error lines.
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
CMP="taskset -c 80-87 /home/alex/mc-env/bin/python3 $S/src-branch/docs/issue85_laneC/compare_output_trees.py"
ALLOW=(--allow-added-log-line 'Staging this movie as native' --allow-added-log-line 'Released native'
       --allow-added-log-line 'WARNING: resident retry preparation did not complete' --allow-added-log-line 'CUDA Error in')
mkdir -p $S/cmp
while read fam a b; do
  [ -z "$fam" ] && continue
  for mode in full products; do
    if [ $mode = full ]; then x=("${ALLOW[@]}"); else x=(--products-only); fi
    $CMP $S/runs/$a $S/runs/$b --manifest $S/inputs/manifest_$fam.json --json-out $S/cmp/${a}__${b}__$mode.json "${x[@]}" > /tmp/cmp.out 2>&1
    echo -e "$fam\t$a\t$b\t$mode\trc=$?\t$(grep -o 'status=[A-Z]*; different files=[0-9]*' /tmp/cmp.out)"
  done
done
