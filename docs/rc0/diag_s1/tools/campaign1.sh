#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1
for f in e10216 e12963 e10474f3 e10641 tutorial e10361; do
  ~/.mc-venv/bin/python tools/diag_run.py --family $f --label $f-L-cpu --binary /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr
  ~/.mc-venv/bin/python tools/diag_run.py --family $f --label $f-L-cuda --binary /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-nvcomp/motioncorr --gpu
done
echo CAMPAIGN1-DONE
