#!/bin/bash
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
B=$S/build; DB=$B/cuda-1db/motioncorr; SHIM=$B/cuda-branch/motioncorr_resident_retry_fault
cd $S
# 1) negative controls: each mutant must fail the strict full-tree comparison it is aimed at
until [ "$(grep -c 'build m' $B/cuda-mut.status 2>/dev/null)" = 2 ]; do sleep 20; done
./runfam3.sh $B/motioncorr-mut-m3 e10641u b4_e10641u_m3_g1
./runfam3.sh $B/motioncorr-mut-m3 e10641u b4_e10641u_m3_g4 --group_frames 4
./runfam3.sh $B/motioncorr-mut-m4 e10641u b4_e10641u_m4_g1
./runfam3.sh $B/motioncorr-mut-m4 e10641u b4_e10641u_m4_g4 --group_frames 4
# 2) dataset level, mixed batch [tutorial, 10641, tutorial, 10641]
./rundataset2.sh $DB d1 1
./rundataset2.sh $DB d2 2
MCENV="MC_PREPROCESS_FAULT=resident-retry-fatal MC_FAULT_ONLY_CVD=b2cb2c39" ./rundataset2.sh $SHIM dpoison 2
MCENV="MC_PREPROCESS_FAULT=none MC_RESIDENT_RETRY_COUNT=1" ./rundataset2.sh $SHIM dshim 2
echo done > runs/BATCH4DONE
