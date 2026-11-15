#!/bin/bash
set -u
W=/mnt/clathrin/alex-motioncorr-hygiene239
export PATH=/home/alex/.mc-venv/bin:$PATH OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset CUDA_VISIBLE_DEVICES PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
for ((i=0;i<180;i++)); do
  [ -f "$W/logs/ctest-nvcomp.exit" ] && break
  sleep 10
done
[ -f "$W/logs/ctest-nvcomp.exit" ] || exit 90
flock -n /tmp/motioncorr-bench.lock true || exit 91
mkdir "$W/cpu-profiling-rerun-started" || exit 92
{ date -u; uptime; ps -eo pid,psr,pcpu,args --sort=-pcpu | head -15; } > "$W/logs/cpu-profiling-rerun-occupancy.txt"
cd "$W/src" || exit 93
taskset -c 112-119 ctest --test-dir "$W/build-cpu" -R '^ProfilingKit$' --output-on-failure --output-junit "$W/logs/ctest-cpu-profiling-rerun.xml" > "$W/logs/ctest-cpu-profiling-rerun.log" 2>&1
rc=$?
echo "$rc" > "$W/logs/ctest-cpu-profiling-rerun.exit"
echo "CPU ProfilingKit permitted rerun rc=$rc"
tail -8 "$W/logs/ctest-cpu-profiling-rerun.log"
exit "$rc"
