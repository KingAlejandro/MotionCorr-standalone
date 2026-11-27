#!/bin/bash
# S1.3c parts 2 and 4 on 4GPUs (lane GPU2).
#  Part 2 (S1.3 inputs, 5x5): CUDA diag4 with the global C2R projection, (a) with CPU's
#   global trajectory injected and (b) with its own; per-frame records + patch map dumps.
#  Part 4 (sweep inputs, config G, --save_noDW): CPU prod + CUDA diag4 off/glob/dw/globdw.
set -u
S=/mnt/clathrin/alex-motioncorr-s1ccf
PY=/home/alex/.mc-venv/bin/python3
B=$S/build-diag4-nvcomp/motioncorr
ALL=""; for y in 1 2 3 4 5; do for x in 1 2 3 4 5; do ALL="$ALL;$y,$x"; done; done; ALL=${ALL#;}
for fam in e10216 e12963; do
  for mode in injcpu-herm own-herm; do
    l=$fam-p5-d4-cuda-$mode
    [ -f $S/runs/$l/run.json ] && { echo "skip $l"; continue; }
    rm -rf $S/runs/$l $S/maps/$l; mkdir -p $S/runs/$l $S/maps/$l
    extra=(); [ $mode = injcpu-herm ] && extra=(--env MC_DIAG_GLOBAL_SHIFTS=$S/shifts/$fam-cpu.txt)
    $PY $S/tools/run.py --family $fam --patches 5 --label $l --gpu --binary $B "${extra[@]}" \
      --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1 --env MC_DIAG_CCF=$S/runs/$l/ccf.txt --env MC_DIAG_MAPS=$S/maps/$l \
      --env "MC_DIAG_MAP_PATCHES=$ALL"
  done
done
for m in e10216-00 e12963-00; do
  $PY $S/tools/run_c.py --sweep-label $m-p5-F-cpu --label e-$m-G-cpu --binary $S/build-prod-cpu/motioncorr --config G --save-nodw
  $PY $S/tools/run_c.py --gpu --sweep-label $m-p5-F-cuda --label e-$m-G-off --binary $B --config G --save-nodw
  $PY $S/tools/run_c.py --gpu --sweep-label $m-p5-F-cuda --label e-$m-G-glob --binary $B --config G --save-nodw --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1
  $PY $S/tools/run_c.py --gpu --sweep-label $m-p5-F-cuda --label e-$m-G-dw --binary $B --config G --save-nodw --env MC_DIAG_C2R_HERMITIAN_DW=1
  $PY $S/tools/run_c.py --gpu --sweep-label $m-p5-F-cuda --label e-$m-G-globdw --binary $B --config G --save-nodw --env MC_DIAG_C2R_HERMITIAN_GLOBAL=1 --env MC_DIAG_C2R_HERMITIAN_DW=1
done
echo CAMPAIGN-E-DONE
