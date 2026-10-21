#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-hygiene246
export PATH=/home/alex/.mc-venv/bin:$PATH TMPDIR=/tmp OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
unset CUDA_VISIBLE_DEVICES PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
mkdir -p "$W/logs"
exec 9>/tmp/motioncorr-bench.lock
flock -w 600 9 || exit 91
# Compiler-presence controls would stall other agents' unfixed selftests.
# Let active selftests finish; the bench lock prevents new compliant batches.
for ((i=0;i<120;i++)); do
  if ! pgrep -f '/mcprof[.]py selftest' >/dev/null; then break; fi
  sleep 5
done
if pgrep -af '/mcprof[.]py selftest'; then echo 'foreign selftests still active; no control started'; exit 92; fi
{ date -u; hostname; uptime; ps -eo user,pid,psr,pcpu,args --sort=-pcpu | sed -n '1,16p'; df -h /mnt/clathrin; } > "$W/logs/occupancy.txt"
for arm in before after; do
  git -C "$W/src-$arm" rev-parse HEAD > "$W/logs/source-$arm.txt"
  [ -z "$(git -C "$W/src-$arm" status --porcelain)" ]
  taskset -c 72-79 cmake -S "$W/src-$arm" -B "$W/build-$arm" -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 > "$W/logs/configure-$arm.log" 2>&1
  echo "configure $arm rc=0"
  set +e
  taskset -c 72-79 ctest --test-dir "$W/build-$arm" -R '^ProfilingKit$' --output-on-failure --output-junit "$W/logs/ctest-$arm.xml" > "$W/logs/ctest-$arm.log" 2>&1
  rc=$?
  set -e
  echo "$rc" > "$W/logs/ctest-$arm.exit"
  echo "ProfilingKit $arm rc=$rc"
  if [ "$arm" = before ]; then [ "$rc" != 0 ]; else [ "$rc" = 0 ]; fi
  [ -z "$(git -C "$W/src-$arm" status --porcelain)" ]
done
{ date -u; echo 'No GPU execution; taskset 72-79; TMPDIR=/tmp; dummy children terminated and reaped by test finally blocks'; } > "$W/logs/completion.txt"
