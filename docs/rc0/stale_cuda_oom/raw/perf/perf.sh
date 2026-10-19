#!/bin/bash
# Paired timing, main 71ab841e vs fix, identical Release sm80+nvCOMP builds. mcprof takes the bench and GPU3 locks itself per invocation.
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W/src-fix
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH; unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES
M=$W/build-main-nvcomp/motioncorr; F=$W/build-fix-nvcomp/motioncorr
K="python3 tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 8 --max-rounds 12 --warmup 1"
TUT=/home/alex/motioncorr-validation-20261011-vm/tutorial-data
G="--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp"
E="--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact"
run() { name=$1; shift; echo "=== $name $(date -u +%FT%TZ)"; $K "$@" > $W/perf/$name.out 2>&1; echo "rc=$? $(date -u +%FT%TZ)"; grep -i "verdict\|resolved\|identity" $W/perf/$name.out | head -5; }
mkdir -p $W/perf
run tutG-ab   main=$M fix=$F --data $TUT --work $W/perf/tutG-ab -- $G
run tutG-null mainA=$M mainB=$M --data $TUT --work $W/perf/tutG-null -- $G
run tutL-ab   main=$M fix=$F --data $TUT --work $W/perf/tutL-ab -- $G --patch_x 5 --patch_y 5
run tutL-null mainA=$M mainB=$M --data $TUT --work $W/perf/tutL-null -- $G --patch_x 5 --patch_y 5
run e10216L-ab   main=$M fix=$F --data $W/perf-e10216 --work $W/perf/e10216L-ab -- $E
run e10216L-null mainA=$M mainB=$M --data $W/perf-e10216 --work $W/perf/e10216L-null -- $E
echo PERF_DONE
