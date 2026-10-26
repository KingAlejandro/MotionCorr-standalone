#!/bin/bash
set -eu
S=/mnt/clathrin/alex-motioncorr-254-review-20261021
for attempt in $(seq 1 180); do
 if test -f "$S/logs/ctest-nvcomp.exit"; then
  export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
  export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib
  set +e
  taskset -c 80-87 ctest --test-dir "$S/build-nvcomp" -R '^CiFailClosedControls$' --output-on-failure --output-junit "$S/logs/ctest-nvcomp-git-fixture-rerun.xml" > "$S/logs/ctest-nvcomp-git-fixture-rerun.log" 2>&1
  echo $? > "$S/logs/ctest-nvcomp-git-fixture-rerun.exit"
  exit 0
 fi
 sleep 5
done
exit 1
