#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1
until grep -q CAMPAIGN1-DONE campaign1.out; do sleep 10; done
for mi in 10 20; do for f in e10216 e10474f3 e12963; do
  ~/.mc-venv/bin/python tools/diag_run.py --family $f --label $f-L-cpu-mi$mi --binary /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr --extra "--max_iter $mi"
  ~/.mc-venv/bin/python tools/diag_run.py --family $f --label $f-L-cuda-mi$mi --binary /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-nvcomp/motioncorr --gpu --extra "--max_iter $mi"
done; done
echo CAMPAIGN2-DONE
