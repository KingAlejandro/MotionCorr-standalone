#!/bin/bash
set -u
S=/mnt/clathrin/alex-motioncorr-peakfit
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
export TMPDIR=$S/tmp
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
exec 8>/tmp/motioncorr-bench.lock;flock -s 8
run() { label=$1;shift
 printf '%q ' "$@" > $S/logs/$label.command;echo >> $S/logs/$label.command
 "$@" > $S/logs/$label.log 2>&1;rc=$?
 echo $rc > $S/logs/$label.exit
 echo "$label rc=$rc $(date -u +%FT%TZ)" >> $S/logs/postvalidation-progress.txt
}
run ctest-cpu-git taskset -c 40-47 ctest --test-dir $S/build-cpu --output-on-failure --output-junit $S/logs/ctest-cpu-git.xml -j1
run tier-A env PYTHON=/home/alex/.mc-venv/bin/python3 taskset -c 40-47 bash $S/src-fix/tools/run_regression_tests.sh $S/build-cpu/motioncorr
run known-motion-cpu taskset -c 40-47 /home/alex/.mc-venv/bin/python3 $S/src-fix/tools/run_known_motion_gates.py --binary $S/build-cpu/motioncorr --outdir $S/known-motion-cpu --fixtures $S/known-motion-cpu-fixtures --json $S/logs/known-motion-cpu.json
exec 7>/tmp/motioncorr-gpu0-correctness.lock;flock 7
# Refresh this test target after the test-only additions, without changing production code.
run build-peak-fit-final taskset -c 40-47 cmake --build $S/build-cuda -j8 --target cuda_peak_fit cuda_peak_fit_float_denominator
run peak-fit-fixed taskset -c 40-47 $S/build-cuda/cuda_peak_fit
run peak-fit-mutant-normal taskset -c 40-47 $S/build-cuda/cuda_peak_fit_float_denominator
run peak-fit-mutant-expected taskset -c 40-47 $S/build-cuda/cuda_peak_fit_float_denominator --expect-mismatch
run known-motion-cuda taskset -c 40-47 /home/alex/.mc-venv/bin/python3 $S/src-fix/tools/run_known_motion_gates.py --binary $S/build-cuda/motioncorr --gpu 0 --outdir $S/known-motion-cuda --fixtures $S/known-motion-cuda-fixtures --json $S/logs/known-motion-cuda.json
flock -u 7
echo DONE >> $S/logs/postvalidation-progress.txt
