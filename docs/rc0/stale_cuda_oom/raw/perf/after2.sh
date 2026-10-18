#!/bin/bash
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11; cd $W
until grep -q DRIVE2_DONE drive2.out 2>/dev/null; do sleep 30; done
export QF_W=$W QF_CPUS=88-95 QF_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d QF_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
echo "compilers running: cc1plus=$(pgrep -x cc1plus | wc -l) nvcc=$(pgrep -x nvcc | wc -l) at $(date -u +%T)"
bash ./run_ctest.sh cuda rerun-profilingkit "^ProfilingKit$"; echo "rerun exit=$(cat ctest-fix-cuda-rerun-profilingkit.exit)"; grep "tests passed" ctest-fix-cuda-rerun-profilingkit.log
./perf2.sh
