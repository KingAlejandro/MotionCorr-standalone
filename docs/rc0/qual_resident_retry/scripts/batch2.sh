#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
SHIM=$S/build/cuda-branch/motioncorr_resident_retry_fault
cd $S
for fam in e10641u e10216; do
 MCENV="MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=none" ./runfam2.sh $SHIM $fam b2_${fam}_count
 MCENV="MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=resident-retry-recoverable" ./runfam2.sh $SHIM $fam b2_${fam}_rec
 MCENV="MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=resident-retry-fatal" ./runfam2.sh $SHIM $fam b2_${fam}_fatal
done
echo done > runs/BATCH2DONE
