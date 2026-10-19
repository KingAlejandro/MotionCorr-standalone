#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1
until grep -q CAMPAIGN2-DONE campaign2.out; do sleep 10; done
R="~/.mc-venv/bin/python tools/diag_run.py"
P=/home/alex/.mc-venv/bin/python
DC=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag-cpu/motioncorr; DG=/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-diag-nvcomp/motioncorr
# A: neutrality of the diagnostic build (env unset) and run-to-run repeat of production CUDA
$P tools/diag_run.py --family e10216 --label e10216-L-diagcpu-noenv --binary $DC
$P tools/diag_run.py --family e10216 --label e10216-L-diagcuda-noenv --binary $DG --gpu
$P tools/diag_run.py --family e10216 --label e10216-L-cuda-repeat --binary /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-nvcomp/motioncorr --gpu
# A2: per-patch dumps (log-only change) for every patch, both backends
for f in e10216 e10474f3 e12963 e10641 tutorial; do
  $P tools/diag_run.py --family $f --label $f-L-diagcpu-dump --binary $DC --env MC_DIAG_DUMP=1
  $P tools/diag_run.py --family $f --label $f-L-diagcuda-dump --binary $DG --gpu --env MC_DIAG_DUMP=1
done
# B: causal drop test -- remove the flipped patch from the side that kept it
$P tools/diag_run.py --family e10216 --label e10216-L-diagcpu-drop14 --binary $DC --env MC_DIAG_DUMP=1 --env "MC_DIAG_DROP=(1,4)"
$P tools/diag_run.py --family e10474f3 --label e10474f3-L-diagcuda-drop12 --binary $DG --gpu --env MC_DIAG_DUMP=1 --env "MC_DIAG_DROP=(1,2)"
$P tools/diag_run.py --family e12963 --label e12963-L-diagcuda-drop41 --binary $DG --gpu --env MC_DIAG_DUMP=1 --env "MC_DIAG_DROP=(4,1)"
$P tools/diag_run.py --family e12963 --label e12963-L-diagcpu-drop25-52 --binary $DC --env MC_DIAG_DUMP=1 --env "MC_DIAG_DROP=(2,5)(5,2)"
$P tools/diag_run.py --family e12963 --label e12963-L-diagcuda-drop41-25-52 --binary $DG --gpu --env MC_DIAG_DUMP=1 --env "MC_DIAG_DROP=(4,1)(2,5)(5,2)"
# C: longevity at 116eb04a (first-parent predecessor of the programme merges)
for f in e10216 e10474f3 e12963; do
  $P tools/diag_run.py --family $f --label $f-L-116cpu --binary /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-116-cpu/motioncorr
  $P tools/diag_run.py --family $f --label $f-L-116cuda --binary /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/build-116-nvcomp/motioncorr --gpu
done
echo CAMPAIGN3-DONE
