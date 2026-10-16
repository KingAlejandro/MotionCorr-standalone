#!/bin/bash
set -u
cd /home/ubuntu/fix178-20261016
for arm in base candidate; do
  flock -w 3600 /tmp/motioncorr-cpu64-bench.lock -c "cd /home/ubuntu/fix178-20261016; date -u; uptime; ps -eo pid,pcpu,comm --sort=-pcpu | head; ~/.mc-venv/bin/cmake -S $arm -B $arm/build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3 && ~/.mc-venv/bin/cmake --build $arm/build --parallel 8" >evidence/$arm-build.log 2>&1
  rc=$?; echo $rc >evidence/$arm-build.exit
  [ $rc = 0 ] || exit $rc
done
flock -w 3600 /tmp/motioncorr-cpu64-bench.lock -c 'cd /home/ubuntu/fix178-20261016; ~/.mc-venv/bin/ctest --test-dir candidate/build -R CpuUnweightedStream -V' >evidence/linux-witness.log 2>&1
echo $? >evidence/linux-witness.exit
