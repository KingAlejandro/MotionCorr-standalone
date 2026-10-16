#!/bin/bash
# Paired profiling-kit compare, main 116eb04a vs candidate c2fcb409 (binary = steps 1+2). The kit takes the bench and gpu locks itself.
W=/home/alex/mc-small; U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54; WU=$W/wu
OUT=$WU/runs-kit24
rm -rf $OUT.pre.txt $OUT.log
taskset -c 120-121 python3 $W/kit/tools/profiling/mcprof.py compare main=$WU/b-t-main/motioncorr cand=$WU/b-t-c2/motioncorr \
  --data $W/data96 --star movies.star --movies 24 --work $OUT --cpus 96-103 --gpu-uuid $U --runner-cpus 120-121 \
  --source main=$WU/src-main --source cand=$WU/src-c4 --commit main=116eb04a --commit cand=c2fcb409 \
  --lock-timeout 28800 --settle-timeout 600 --pairs 12 --profile-pass 3 -- \
  --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --skip_report_pdf \
  > $OUT.log 2>&1
echo "KIT-DONE rc=$?" >> $OUT.log
