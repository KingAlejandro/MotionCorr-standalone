#!/usr/bin/env bash
# round96 correctness-foundation integration -- CPU validation phase 2
# (a) rerun the fail-closed chain with cmake on PATH
# (b) negative controls: missing required test, missing required script,
#     corrupted canonical fixture
# (c) discriminating control: the candidate's NEW tests against BASE main source
set -uo pipefail
ROOT=/home/ubuntu/mc-i96-integration
VENV=/home/ubuntu/.mc-venv
export PATH=$VENV/bin:$PATH
LOG=$ROOT/logs
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
J=16
exec > >(tee -a "$LOG/phase2.log") 2>&1
echo "##### PHASE 2 START #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
grep -E "Cpus_allowed_list" /proc/self/status; numactl --show | grep -E "membind|physcpubind" 
echo "cmake on PATH: $(command -v cmake)"

cd "$ROOT/src"
echo
echo "##### (a) FAIL-CLOSED CHAIN, cmake on PATH #####"
echo "--- \$ tools/test_ci_fail_closed.py -v"
python3 tools/test_ci_fail_closed.py -v 2>&1 | tail -20
echo "--- \$ ctest (full suite) ---"
( cd build && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 2>&1 | tail -22 )

echo
echo "##### (b) NEGATIVE CONTROLS on the candidate #####"
NC=$ROOT/negative; rm -rf "$NC"; mkdir -p "$NC"

echo "--- N1a: required test CiFailClosedControls de-registered -> collection must fail"
cp -r "$ROOT/src" "$NC/n1a" && rm -rf "$NC/n1a/build" "$NC/n1a/.git"
python3 - "$NC/n1a/CMakeLists.txt" <<'PY'
import sys,re
p=sys.argv[1]; s=open(p).read()
s=s.replace('''        add_test(NAME CiFailClosedControls
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/test_ci_fail_closed.py)
''','')
open(p,'w').write(s)
PY
cmake -S "$NC/n1a" -B "$NC/n1a/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 >/dev/null 2>&1
python3 tools/validate_test_collection.py --test-dir "$NC/n1a/build" 2>&1 | tail -4
echo "N1a exit=${PIPESTATUS[0]} (expected 1)"

echo "--- N1b: required test WriteFaults de-registered -> collection must fail (union bites)"
cp -r "$ROOT/src" "$NC/n1b" && rm -rf "$NC/n1b/build" "$NC/n1b/.git"
python3 - "$NC/n1b/CMakeLists.txt" <<'PY'
import sys
p=sys.argv[1]; s=open(p).read()
s=s.replace('''        add_test(NAME WriteFaults
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_write_faults.py
                --binary $<TARGET_FILE:motioncorr>)
''','')
open(p,'w').write(s)
PY
cmake -S "$NC/n1b" -B "$NC/n1b/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 >/dev/null 2>&1
python3 tools/validate_test_collection.py --test-dir "$NC/n1b/build" 2>&1 | tail -4
echo "N1b exit=${PIPESTATUS[0]} (expected 1)"

echo "--- N2: required script tools/verify_fixtures.py removed -> preflight must fail"
cp -r "$ROOT/src" "$NC/n2" && rm -rf "$NC/n2/build" "$NC/n2/.git"
rm -f "$NC/n2/tools/verify_fixtures.py"
python3 tools/ci_preflight.py --repo "$NC/n2" 2>&1 | tail -4
echo "N2 exit=${PIPESTATUS[0]} (expected 1)"

echo "--- N3: one byte flipped in a canonical fixture -> verification must fail"
cp -r "$ROOT/src" "$NC/n3" && rm -rf "$NC/n3/build"
( cd "$NC/n3" && python3 tools/verify_fixtures.py >/dev/null 2>&1; echo "    baseline verify exit=$? (expected 0, must pass BEFORE corruption)" )
python3 - "$NC/n3/test-data/known_motion/km_global_hisnr.mrcs" <<'PY'
import sys
p=sys.argv[1]
b=bytearray(open(p,'rb').read())
off=len(b)//2
old=b[off]; b[off]^=0x01
open(p,'wb').write(bytes(b))
print(f"    flipped byte at offset {off}: {old:#04x} -> {b[off]:#04x}")
PY
( cd "$NC/n3" && python3 tools/verify_fixtures.py 2>&1 | tail -6; echo "N3 exit=${PIPESTATUS[0]} (expected nonzero)" )

echo
echo "##### (c) DISCRIMINATING CONTROL: candidate tests against BASE main source #####"
echo "Base src/ (unfixed) + candidate tests/, tools/, CMakeLists.txt, test-data/."
echo "The three integrated groups' new tests MUST fail here, or they are green by construction."
OLD=$ROOT/oldsrc; rm -rf "$OLD"
git -C "$ROOT/src" worktree add -q --detach "$OLD" "$BASE" 2>&1 | tail -2
cd "$OLD"
git checkout -q "$(git -C "$ROOT/src" rev-parse HEAD)" -- tests tools CMakeLists.txt test-data .github
echo "--- confirm src/ is base and tests/ is candidate ---"
echo "src/image.h      sha256: $(sha256sum src/image.h | cut -c1-16)  (base $(git show $BASE:src/image.h | sha256sum | cut -c1-16))"
echo "src/rwMRC.h      sha256: $(sha256sum src/rwMRC.h | cut -c1-16)  (base $(git show $BASE:src/rwMRC.h | sha256sum | cut -c1-16))"
echo "src/rwTIFF.h     sha256: $(sha256sum src/rwTIFF.h | cut -c1-16)  (base $(git show $BASE:src/rwTIFF.h | sha256sum | cut -c1-16))"
cmake -S "$OLD" -B "$OLD/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/nc-configure.log" 2>&1
echo "negative-control configure exit=$?"
cmake --build "$OLD/build" --parallel $J > "$LOG/nc-build.log" 2>&1
NCB=$?
echo "negative-control build exit=$NCB"
if [ $NCB -ne 0 ]; then
  echo "!! build failed -- a control that does not build cannot detect anything. Last errors:"
  grep -E "error:" "$LOG/nc-build.log" | tail -10
fi
( cd "$OLD/build" && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 > "$LOG/nc-ctest.log" 2>&1; echo "negative-control ctest exit=$?" )
grep -E "^ *[0-9]+/[0-9]+ Test|tests passed|tests failed" "$LOG/nc-ctest.log"
echo "--- which tests FAILED on base source (these are the ones that detect the defects) ---"
grep -E "\*\*\*(Failed|Not Run|Exception)" "$LOG/nc-ctest.log" || echo "(none -- controls do NOT discriminate)"

echo
echo "##### DONE PHASE 2 #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
