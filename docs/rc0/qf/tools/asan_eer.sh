#!/bin/bash
# QF item 15b: EerMemorySafety (#231, D10) under ASan+UBSan on the frozen SHA. CPU build only, no GPU.
# Required: QF_W (holds src/, the frozen checkout), QF_SHA, QF_CPUS. Gated on the bench lock (probe only).
# Builds $QF_W/build-asan with #231's sanitizer flags (RelWithDebInfo, -fsanitize=address,undefined
# -fno-omit-frame-pointer), checks the binary is instrumented, runs ctest -R '^EerMemorySafety$' with
# default sanitizer options (the test fails on any AddressSanitizer, LeakSanitizer or "runtime error:"
# line in a child log), and records whether F's EER decoder sources equal #231's tested code 97fb9fda
# (item 15c). Writes $QF_W/asan-eer.{log,exit}; exit status = verdict (0 PASS).
set -u
: "${QF_W:?}" "${QF_SHA:?}" "${QF_CPUS:?}"
W=$QF_W SRC=$QF_W/src B=$QF_W/build-asan O=$QF_W/asan-eer
D10_TESTED=97fb9fda   # #231's tested code head (src unchanged to its merge head 9d241833)
DECODER="src/renderEER.cpp src/renderEER.h src/rwMRC.h src/strings.cpp"
export PATH=/home/alex/.mc-venv/bin:$PATH
unset ASAN_OPTIONS UBSAN_OPTIONS LSAN_OPTIONS PYTHONOPTIMIZE
cd $SRC || exit 90
[ "$(git rev-parse HEAD)" = "$QF_SHA" ] || { echo "HEAD != QF_SHA" | tee $O.log; echo 91 > $O.exit; exit 91; }
[ -z "$(git status --porcelain)" ] || { echo "source tree not clean" | tee $O.log; echo 92 > $O.exit; exit 92; }
until flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held, waiting $(date -u +%T)" >> $O.waits; sleep 60; done
mkdir -p $W/logs; v=0
{
  echo "start $(date -u +%FT%TZ) HEAD=$(git rev-parse HEAD) status=$(git status --porcelain | wc -l) mask=$QF_CPUS"
  SAN='-fsanitize=address,undefined -fno-omit-frame-pointer'
  taskset -c $QF_CPUS cmake -S $SRC -B $B -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DCUDA=OFF \
      -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3 "-DCMAKE_CXX_FLAGS=$SAN" "-DCMAKE_C_FLAGS=$SAN" \
      -DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined > $W/logs/configure-asan.log 2>&1
  rc=$?; echo "configure rc=$rc"; [ $rc = 0 ] || v=1
  taskset -c $QF_CPUS cmake --build $B -j8 > $W/logs/build-asan.log 2>&1
  rc=$?; echo "build rc=$rc $(date -u +%FT%TZ)"; [ $rc = 0 ] || v=1
  grep CMAKE_HOME_DIRECTORY $B/CMakeCache.txt
  grep -h CXX_FLAGS $B/CMakeFiles/motioncorr.dir/flags.make
  grep -q -- '-fsanitize=address,undefined' $B/CMakeFiles/motioncorr.dir/flags.make || { echo "flags.make lacks -fsanitize"; v=1; }
  for b in motioncorr runner_numerics; do
    echo "$b sha256: $(sha256sum $B/$b | cut -c1-64)"
    ldd $B/$b | grep -q libasan && ldd $B/$b | grep -q libubsan || { echo "$b not linked to libasan+libubsan"; v=1; }
  done
  taskset -c $QF_CPUS ctest --test-dir $B -R '^EerMemorySafety$' --output-on-failure > $O.ctest.log 2>&1
  rc=$?; cat $O.ctest.log; echo "ctest rc=$rc"
  [ $rc = 0 ] && grep -q '100% tests passed, 0 tests failed out of 1$' $O.ctest.log || v=1
  if git diff --quiet $D10_TESTED HEAD -- $DECODER; then
    echo "decoder sources == $D10_TESTED: yes"
  else
    echo "decoder sources == $D10_TESTED: NO"; git diff --stat $D10_TESTED HEAD -- $DECODER
  fi
  echo "verdict $([ $v = 0 ] && echo PASS || echo FAIL) end $(date -u +%FT%TZ)"
} > $O.log 2>&1
echo $v > $O.exit
tail -1 $O.log
exit $v
