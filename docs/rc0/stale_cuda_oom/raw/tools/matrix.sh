#!/bin/bash
# In-product D1 matrix on GPU3. Each run: python d11_run.py <bin> <label> <inputs> <star> <free> <ingest>
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
R() { flock /tmp/motioncorr-gpu3-correctness.lock ~/.mc-venv/bin/python3 -I d11_run.py "$@"; }
until flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held $(date -u +%T)"; sleep 60; done
for a in main fix; do
  B=$W/build-$a-nvcomp/motioncorr
  R $B $a-S1 $W/inputs s1.star 8.5 auto
  R $B $a-S2 $W/inputs s2.star 8.5 nvcomp
  R $B $a-S3 $W/inputs s3.star 8.5 auto
  R $B $a-S4 $W/inputs s4.star 16 auto
done
B=$W/build-fix-nvcomp/motioncorr
for m in tut26 tut27 e10164; do R $B ref-$m $W/inputs $m.star none auto; R $B ref-$m-at8.5 $W/inputs $m.star 8.5 auto; done
R $B ref-tut26-at16 $W/inputs tut26.star 16 auto
R $B ref-e10164-at16 $W/inputs e10164.star 16 auto
for m in tut26 tut27; do R $B ref-$m-nvcomp $W/inputs $m.star none nvcomp; R $B ref-$m-nvcomp-at8.5 $W/inputs $m.star 8.5 nvcomp; done
B=$W/build-main-nvcomp/motioncorr
for m in tut26 e10164; do R $B mainref-$m $W/inputs $m.star none auto; done
echo MATRIX_DONE
