#!/usr/bin/env bash
# round96 correctness-foundation -- FINAL-HEAD CPU validation (all four groups).
# Fresh clone of the final head, full suite, negative controls, and the
# healthy all-24 A/B against exact current main.
set -uo pipefail
ROOT=/home/ubuntu/mc-i96-final
VENV=/home/ubuntu/.mc-venv
export PATH=$VENV/bin:$PATH
BUNDLE=/home/ubuntu/mc-i96-final.bundle
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
TUT=/home/ubuntu/mc51/tutorial
J=16
rm -rf "$ROOT"; mkdir -p "$ROOT/logs"; LOG=$ROOT/logs
exec > >(tee -a "$LOG/final.log") 2>&1
echo "##### FINAL-HEAD CPU VALIDATION #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
numactl --show | grep -E "physcpubind|membind|nodebind"
echo "SMT thread(s)/core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}') ; node1 = CPUs 32-63"
echo "load: $(cat /proc/loadavg)"
for p in $(pgrep -x ctffind); do echo "interference ctffind pid=$p cpus=$(awk '/Cpus_allowed_list/{print $2}' /proc/$p/status) (recorded, untouched)"; done
g++ --version|head -1; cmake --version|head -1; python3 --version; python3 -c "import numpy;print('numpy',numpy.__version__)"
pkg-config --modversion libtiff-4 | sed 's/^/libtiff-4 /'

sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" "$ROOT/src"
cd "$ROOT/src"
echo "final head: $(git rev-parse HEAD)"; echo "tree: $(git rev-parse HEAD^{tree})"
echo "commits over base: $(git log --oneline $BASE..HEAD | wc -l)"
echo "tracked-source digest: $(git ls-files src tests tools CMakeLists.txt .github test-data | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)"

echo; echo "##### BUILD #####"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/cfg.log" 2>&1
echo "configure exit=$?"
grep -E "^CMAKE_BUILD_TYPE|^CMAKE_CXX_FLAGS_RELEASE" build/CMakeCache.txt
cmake --build build --parallel $J > "$LOG/build.log" 2>&1
echo "build exit=$?  errors=$(grep -cE 'error:' "$LOG/build.log")  warnings=$(grep -ciE 'warning' "$LOG/build.log")"
sha256sum build/motioncorr build/runner_numerics build/image_write_faults build/defect_parser

echo; echo "##### FULL SUITE #####"
( cd build && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 > "$LOG/ctest.log" 2>&1; echo "ctest exit=$?" )
grep -E "^ *[0-9]+/[0-9]+ Test|tests passed|tests failed" "$LOG/ctest.log"
echo "collected:"; ( cd build && ctest --show-only=json-v1 | python3 -c "import json,sys;d=json.load(sys.stdin);ns=[t['name'] for t in d['tests']];print(len(ns));[print('  ',n) for n in ns]" )

echo; echo "##### FAIL-CLOSED CHAIN #####"
for c in "tools/ci_preflight.py" "tools/validate_test_collection.py --test-dir build" "test-data/generate_known_motion_fixture.py --canonical" "tools/verify_fixtures.py" "tools/test_ci_fail_closed.py"; do
  echo "--- \$ python3 $c"; python3 $c > "$LOG/chain.tmp" 2>&1; echo "exit=$?"; tail -3 "$LOG/chain.tmp"
done

echo; echo "##### NEGATIVE CONTROL: final-head tests against BASE source #####"
OLD=$ROOT/oldsrc; rm -rf "$OLD"
git -C "$ROOT/src" worktree add -q --detach "$OLD" "$BASE"
cd "$OLD"
git checkout -q "$(git -C "$ROOT/src" rev-parse HEAD)" -- tests tools CMakeLists.txt test-data .github
echo "src/ is base: image.h $( [ "$(sha256sum < src/image.h)" = "$(git show $BASE:src/image.h | sha256sum)" ] && echo yes || echo NO )  motioncorr_runner.cpp $( [ "$(sha256sum < src/motioncorr_runner.cpp)" = "$(git show $BASE:src/motioncorr_runner.cpp | sha256sum)" ] && echo yes || echo NO )"
cmake -S "$OLD" -B "$OLD/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/nc-cfg.log" 2>&1
echo "nc configure exit=$?"
cmake --build "$OLD/build" --parallel $J > "$LOG/nc-build.log" 2>&1
echo "nc build exit=$?  (a control that does not build detects nothing)"
( cd "$OLD/build" && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 > "$LOG/nc-ctest.log" 2>&1; echo "nc ctest exit=$?" )
grep -E "tests passed|tests failed" "$LOG/nc-ctest.log"
echo "tests that FAIL on base source (these detect the integrated defects):"
grep -E "\*\*\*(Failed|Not Run|Exception)|Subprocess aborted" "$LOG/nc-ctest.log" || echo "  (NONE -- controls do not discriminate)"

echo; echo "##### HEALTHY ALL-24 A/B AT FINAL HEAD #####"
REF=$ROOT/refsrc; rm -rf "$REF"
git -C "$ROOT/src" worktree add -q --detach "$REF" "$BASE"
cmake -S "$REF" -B "$REF/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/ref-cfg.log" 2>&1
cmake --build "$REF/build" --parallel $J > "$LOG/ref-build.log" 2>&1
echo "ref build exit=$?  ref dirty=$(git -C "$REF" status --porcelain | wc -l)"
sha256sum "$REF/build/motioncorr" "$ROOT/src/build/motioncorr"
[ "$(sha256sum < "$REF/build/motioncorr")" = "$(sha256sum < "$ROOT/src/build/motioncorr")" ] && echo "!! IDENTICAL -- vacuous" || echo "OK distinct binaries"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
rm -rf "$ROOT/ab24"
python3 "$ROOT/src/docs/io_review_evidence/harness/compare_outputs.py" \
  --repo "$ROOT/src" \
  --ref-binary "$REF/build/motioncorr" --ref-label main-4c952b3 \
  --test-binary "$ROOT/src/build/motioncorr" --test-label integrate-round96-final \
  --tutorial "$TUT" --threads 8 \
  --work "$ROOT/ab24" --json "$ROOT/ab24.json" > "$LOG/ab24.log" 2>&1
echo "A/B exit=$?"
tail -30 "$LOG/ab24.log"
echo "##### DONE FINAL #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
