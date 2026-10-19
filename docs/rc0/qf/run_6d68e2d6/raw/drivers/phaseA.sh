#!/bin/bash
# QF phase A: Step 0 builds, items 1-3 CTest + grades, item 15b ASan. Sentinel: phaseA.done
set -u
source /mnt/clathrin/alex-motioncorr-rc0/W-QF/env.sh
cd $QF_W
{
echo "phaseA start $(date -u +%FT%TZ)"
{ hostname; uname -r; nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader; /usr/local/cuda-12.8/bin/nvcc --version | tail -2; g++ --version | head -1; /home/alex/.mc-venv/bin/cmake --version 2>/dev/null | head -1 || cmake --version | head -1; /home/alex/.mc-venv/bin/python3 -c "import sys,numpy;print(sys.version.split()[0],numpy.__version__)"; gs --version; cat /sys/kernel/mm/transparent_hugepage/enabled; ls /home/alex/nvcomp53; } > build-info.txt 2>&1
bash tools/build.sh > logs/build.out 2>&1; echo "build.sh rc=$?"
grep -q ALL_BUILDS_DONE logs/build.out || { echo "builds incomplete; stop"; echo stop > phaseA.done; exit 1; }
for c in cpu cuda nvcomp; do
  bash tools/run_ctest.sh $c; echo "run_ctest $c exit=$(cat ctest-$c.exit 2>/dev/null)"
  /home/alex/.mc-venv/bin/python3 tools/grade_ctest.py $c; echo "grade $c rc=$?"
done
bash tools/asan_eer.sh; echo "asan_eer rc=$?"
echo "phaseA end $(date -u +%FT%TZ)"
} >> logs/phaseA.log 2>&1
echo done > phaseA.done
