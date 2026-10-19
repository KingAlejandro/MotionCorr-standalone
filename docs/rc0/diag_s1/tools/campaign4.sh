#!/bin/bash
# Round 1 (R-S1): neutrality reruns with retained digests, CCF/tie logging, CPU-tie CUDA variant.
cd /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1
P=/home/alex/.mc-venv/bin/python
R="$P tools/diag_run.py"
PC=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr; PG=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-nvcomp/motioncorr
DC=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag-cpu/motioncorr; DG=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag-nvcomp/motioncorr
D2C=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag2-cpu/motioncorr; D2G=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag2-nvcomp/motioncorr
for f in e10216 e10474f3 e12963 e10641 tutorial; do
  $R --family $f --label r1-$f-L-prod-cpu --binary $PC
  $R --family $f --label r1-$f-L-prod-cuda --binary $PG --gpu
  $R --family $f --label r1-$f-L-diagdump-cpu --binary $DC --env MC_DIAG_DUMP=1
  $R --family $f --label r1-$f-L-diagdump-cuda --binary $DG --gpu --env MC_DIAG_DUMP=1
done
for f in e10216 e10474f3 e12963 tutorial; do
  $R --family $f --label r1-$f-L-d2-noenv-cpu --binary $D2C
  $R --family $f --label r1-$f-L-d2-noenv-cuda --binary $D2G --gpu
  $R --family $f --label r1-$f-L-d2-ccf-cpu --binary $D2C --env MC_DIAG_DUMP=1 --env MC_DIAG_CCF=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/runs/r1-$f-L-d2-ccf-cpu/ccf.txt
  $R --family $f --label r1-$f-L-d2-ccf-cuda --binary $D2G --gpu --env MC_DIAG_DUMP=1 --env MC_DIAG_CCF=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/runs/r1-$f-L-d2-ccf-cuda/ccf.txt
  $R --family $f --label r1-$f-L-d2-ties-cuda --binary $D2G --gpu --env MC_DIAG_CPU_TIES=1
  $R --family $f --label r1-$f-L-d2-ties-ccf-cuda --binary $D2G --gpu --env MC_DIAG_CPU_TIES=1 --env MC_DIAG_DUMP=1 --env MC_DIAG_CCF=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/runs/r1-$f-L-d2-ties-ccf-cuda/ccf.txt
done
echo CAMPAIGN4-DONE
