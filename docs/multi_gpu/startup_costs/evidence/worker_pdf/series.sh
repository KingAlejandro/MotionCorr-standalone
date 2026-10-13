#!/bin/bash
# Runs under: flock /tmp/motioncorr-bench.lock taskset -c 96-103
set -uo pipefail
D=/home/alex/mc-wpdf-20261013
DATA=/home/alex/MotionCorr-standalone/relion30_tutorial
PY=/home/alex/.mc-venv/bin/python3
export PATH=/usr/local/cuda/bin:/home/alex/.mc-venv/bin:$PATH
cd $D
echo "=== VENUE ==="; date -Is; hostname; grep Cpus_allowed_list /proc/self/status; nvcc --version | tail -1; gs --version
for n in base cand; do
  cmake -S src-$n -B build-$n -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=80 -DPython3_EXECUTABLE=$PY > conf-$n.log 2>&1 || { echo "configure $n failed"; exit 1; }
  cmake --build build-$n --parallel 8 > build-$n.log 2>&1 || { echo "build $n failed"; grep -i error build-$n.log | head; exit 1; }
  echo "$n built: $(sha256sum build-$n/motioncorr | cut -c1-16) flag_strings=$(strings build-$n/motioncorr | grep -c -- '--skip_report_pdf') home=$(grep CMAKE_HOME_DIRECTORY build-$n/CMakeCache.txt)"
done
ARGS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --j 4 --seed 1"
mkdir -p runs
for n in base cand; do
  cd $DATA
  t0=$(date +%s.%N)
  strace -f -qq -e trace=execve -o $D/runs/$n.execve.txt \
    $PY $D/src-$n/tools/multi_gpu/run_dataset.py --binary $D/build-$n/motioncorr --star movies.star \
      --out $D/runs/$n --required-products .mrc,.star \
      --launcher-args="--devices 0,1 --cpus 96-99;100-103" -- $ARGS > $D/runs/$n.console.log 2>&1
  rc=$?; t1=$(date +%s.%N)
  cd $D
  echo "$n rc=$rc wall_under_strace=$(echo "$t1-$t0" | bc) gs_execs=$(grep -c 'execve("[^"]*/gs"' runs/$n.execve.txt) motioncorr_execs=$(grep -c 'execve("[^"]*/motioncorr"' runs/$n.execve.txt)"
  grep 'execve("[^"]*/gs"' runs/$n.execve.txt | grep -o '"-sOutputFile=[^"]*"' | sed "s|$D/runs/$n/||" | sort | sed "s/^/  $n gs: /"
done
echo "=== files present in only one arm (whole --out tree) ==="
diff <(cd runs/base && find . -type f | sort) <(cd runs/cand && find . -type f | sort)
echo "=== merged products (compare_output_trees) ==="
$PY src-cand/docs/issue85_laneC/compare_output_trees.py runs/base/merged runs/cand/merged \
  --manifest src-cand/docs/issue85_laneC/tutorial_24_movie_manifest.json --input-star $DATA/movies.star \
  --json-out runs/cmp-merged.json 2>&1 | tail -4
echo CMP_RC=${PIPESTATUS[0]}
echo "=== worker report lines ==="
grep -l "Now generating logfile.pdf" runs/*/_workers/*/*.log runs/*/w*/*.log 2>/dev/null
echo SERIES_DONE
