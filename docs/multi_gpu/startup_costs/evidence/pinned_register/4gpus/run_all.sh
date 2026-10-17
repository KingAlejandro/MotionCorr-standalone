#!/bin/bash
S=/dev/shm/mcs2; cd $S
for r in a b c; do
  echo "queue region $r $(date -Is)" >> $S/run_all.log
  flock -w 36000 /tmp/motioncorr-bench.lock taskset -c 96-103 bash $S/region_$r.sh > $S/region_$r.out 2>&1
  echo "region $r rc=$? $(date -Is)" >> $S/run_all.log
done
echo ALL-DONE >> $S/run_all.log
