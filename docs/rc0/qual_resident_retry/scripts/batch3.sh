#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
B=$S/build; PRE=$B/cuda-pre197/motioncorr; DB=$B/cuda-1db/motioncorr; REV=$B/cuda-rev197/motioncorr; SHIM=$B/cuda-branch/motioncorr_resident_retry_fault
REC="MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=resident-retry-recoverable"
CNT="MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=none"
cd $S
# RSS / VRAM arms, then a second pass on 10641
for pass in a b; do
 for fam in e10641u e10216; do
  [ $pass = b ] && [ $fam = e10216 ] && continue
  ./runfam3.sh $PRE $fam b3${pass}_${fam}_pre
  ./runfam3.sh $DB  $fam b3${pass}_${fam}_db
  [ $pass = a ] && ./runfam3.sh $REV $fam b3${pass}_${fam}_rev
  MCENV="$REC" ./runfam3.sh $SHIM $fam b3${pass}_${fam}_rec
 done
done
# unequal grouping (--group_frames 4: 70 -> 17 groups, last two of 5; 59 -> 14 groups, last three of 5)
./runfam3.sh $PRE e10641u b3g_e10641u_pre --group_frames 4
./runfam3.sh $DB  e10641u b3g_e10641u_db --group_frames 4
./runfam3.sh $REV e10641u b3g_e10641u_rev --group_frames 4
MCENV="$CNT" ./runfam3.sh $SHIM e10641u b3g_e10641u_count --group_frames 4
./runfam3.sh $PRE e10216 b3g_e10216_pre --group_frames 4
./runfam3.sh $DB  e10216 b3g_e10216_db --group_frames 4
MCENV="$CNT" ./runfam3.sh $SHIM e10216 b3g_e10216_count --group_frames 4
echo done > runs/BATCH3DONE
