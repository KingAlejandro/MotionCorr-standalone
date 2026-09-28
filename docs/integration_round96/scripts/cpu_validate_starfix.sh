#!/usr/bin/env bash
# PR110 review follow-up -- canonical STAR immutability fix.
# CPU-only. cpu64, taskset -c 32-63 (NUMA node1), build/runtime <= 16,
# serialized under /tmp/motioncorr-issue96-cpu-validation.lock.
# No GPU build, run or queuing: #53 owns the shared GPU correctness slot.
set -uo pipefail
ROOT=/home/ubuntu/mc-i96-starfix
VENV=/home/ubuntu/.mc-venv
export PATH=$VENV/bin:$PATH
BUNDLE=/home/ubuntu/mc-i96-fix.bundle
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
PREV=f965070                      # PR110 head Codex reviewed (f9650704)
J=16
rm -rf "$ROOT"; mkdir -p "$ROOT/logs"; LOG=$ROOT/logs
exec > >(tee -a "$LOG/starfix.log") 2>&1

echo "##### PROVENANCE #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"; hostname; uname -r
echo "--- actual inherited process cpuset / mems ---"
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
echo "--- actual NUMA policy in force ---"; numactl --show | grep -E "policy|physcpubind|nodebind|membind"
echo "--- lane topology (CPU,NODE,SOCKET,CORE) ---"
lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#' | awk -F, '$1>=32 && $1<=63' | head -4
echo "  ... through CPU 63; Thread(s) per core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}') (1 = no SMT, each logical CPU is a physical core)"
echo "--- load at start ---"; cat /proc/loadavg
echo "--- interference (recorded, untouched) ---"
for p in $(pgrep -x ctffind); do
  echo "  ctffind pid=$p cpus=$(awk '/Cpus_allowed_list/{print $2}' /proc/$p/status) rss=$(awk '/VmRSS/{print $2" "$3}' /proc/$p/status)"
done
echo "  (ctffind not signalled, reniced or reaffinitised by this job)"

echo "--- OBSERVED NUMA memory placement for this lane ---"
python3 - <<'PROBE' &
import os, time
n = 256 * 1024 * 1024
buf = bytearray(n)
for i in range(0, n, 4096):
    buf[i] = 1
open('/tmp/i96_probe_pid', 'w').write(str(os.getpid()))
time.sleep(6)
PROBE
PROBE_BG=$!
sleep 3
PPID_PROBE=$(cat /tmp/i96_probe_pid 2>/dev/null)
if [ -n "${PPID_PROBE:-}" ] && [ -d /proc/$PPID_PROBE ]; then
  echo "  probe pid=$PPID_PROBE cpus=$(awk '/Cpus_allowed_list/{print $2}' /proc/$PPID_PROBE/status)"
  echo "  numa_maps page counts (N<node>=pages), anon heap lines:"
  grep -E "^[0-9a-f]+ (bind|default)" /proc/$PPID_PROBE/numa_maps 2>/dev/null | grep -oE "N[0-9]+=[0-9]+" \
    | awk -F= '{s[$1]+=$2} END {for (k in s) printf "    %s = %d pages (%.1f MiB)\n", k, s[k], s[k]*4096/1048576}'
  numastat -p $PPID_PROBE 2>/dev/null | tail -6
else
  echo "  probe pid unavailable; NUMA placement not observed this run"
fi
wait $PROBE_BG 2>/dev/null

echo "--- toolchain ---"
g++ --version|head -1; cmake --version|head -1; python3 --version
python3 -c "import numpy;print('numpy',numpy.__version__)"

echo; echo "##### SOURCE #####"
sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" "$ROOT/src"
cd "$ROOT/src"
HEAD_SHA=$(git rev-parse HEAD)
echo "final head: $HEAD_SHA"
echo "tree:       $(git rev-parse HEAD^{tree})"
echo "dirty:      $(git status --porcelain | wc -l)"
echo "fix commits over the reviewed head $PREV:"; git log --oneline $PREV..HEAD
echo "changed files vs the reviewed head:"; git diff --stat $PREV..HEAD
echo "payload identity of the three trusted artifact classes:"
for c in km_global_hisnr km_local_hisnr km_local_noisy km_local_nonsquare; do
  printf "  %-20s star=%s truth=%s\n" "$c" \
    "$(sha256sum test-data/known_motion/$c.star | cut -c1-16)" \
    "$(sha256sum test-data/known_motion/${c}_ground_truth.json | cut -c1-16)"
done
echo "  MANIFEST.json = $(sha256sum test-data/known_motion/MANIFEST.json | cut -c1-16)"

echo; echo "##### BUILD (Release, BUILD_TESTING=ON, CUDA=OFF) #####"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF \
      -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/cfg.log" 2>&1
echo "configure exit=$?"
grep -E "^CMAKE_BUILD_TYPE|^CMAKE_CXX_FLAGS_RELEASE" build/CMakeCache.txt
cmake --build build --parallel $J > "$LOG/build.log" 2>&1
echo "build exit=$?  errors=$(grep -cE 'error:' "$LOG/build.log")"
sha256sum build/motioncorr build/defect_parser build/image_write_faults

echo; echo "##### COMBINED SUITE AT FINAL SOURCE #####"
( cd build && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 > "$LOG/ctest.log" 2>&1; echo "ctest exit=$?" )
grep -E "tests passed|tests failed" "$LOG/ctest.log"
grep -E "^ *[0-9]+/[0-9]+ Test" "$LOG/ctest.log"
echo "registered inventory (union must still be 17):"
( cd build && ctest --show-only=json-v1 | python3 -c "import json,sys;print(len(json.load(sys.stdin)['tests']))" )

echo; echo "##### FAIL-CLOSED CHAIN, CI ORDER #####"
for c in "tools/ci_preflight.py" "tools/validate_test_collection.py --test-dir build" "test-data/generate_known_motion_fixture.py --canonical" "tools/verify_fixtures.py"; do
  echo "--- \$ python3 $c"; python3 $c > "$LOG/chain.tmp" 2>&1; echo "exit=$?"; tail -3 "$LOG/chain.tmp"
done
echo "--- canonical run must NOT have modified any committed STAR ---"
git status --porcelain test-data/known_motion/ | sed 's/^/  /'
echo "  (empty = committed STAR and truth files untouched by --canonical)"
echo "--- \$ python3 tools/test_ci_fail_closed.py -v"
python3 tools/test_ci_fail_closed.py -v > "$LOG/controls.log" 2>&1
echo "exit=$?"
grep -E "^test_|Ran [0-9]+ tests|^OK|^FAILED" "$LOG/controls.log"

echo; echo "##### BEFORE/AFTER: does the fix actually change the outcome? #####"
echo "Mutation: VOLTAGE 300.0 -> 200.0. Chosen because VOLTAGE is written ONLY into the"
echo ".star; canonical mode preserves the committed truth JSON, so neither the movie digest"
echo "nor the truth digest can see it. (PIXEL_SIZE is NOT usable for this: it is also passed"
echo "to write_mrc_stack() and lands in the MRC header, so the movie digest already caught"
echo "it. A first pass of this control used PIXEL_SIZE and both heads appeared to detect --"
echo "for the old head that was the movie check, not the STAR. Recorded rather than hidden.)"
OLD=$ROOT/oldsrc; rm -rf "$OLD"
git -C "$ROOT/src" worktree add -q --detach "$OLD" "$PREV"
CANON_MOVIE_SHA=$(python3 -c "import json;print(json.load(open('$ROOT/src/test-data/known_motion/MANIFEST.json'))['cases']['km_global_hisnr']['movie_sha256'])")
echo "canonical movie_sha256 = $CANON_MOVIE_SHA"

run_arm () {  # $1=label  $2=source tree
  local label=$1 tree=$2 wd=$ROOT/arm_$1
  rm -rf "$wd"; mkdir -p "$wd"
  cp "$tree/test-data/known_motion/km_global_hisnr_ground_truth.json" "$wd/"
  cp "$tree/test-data/known_motion/km_global_hisnr.star" "$wd/"
  local before; before=$(sha256sum "$wd/km_global_hisnr.star" | cut -d' ' -f1)
  sed 's/^VOLTAGE = 300.0/VOLTAGE = 200.0/' \
      "$tree/test-data/generate_known_motion_fixture.py" > "$wd/gen_mutated.py"
  python3 "$wd/gen_mutated.py" --case km_global_hisnr --canonical --outdir "$wd" > "$wd/gen.log" 2>&1
  local gen_rc=$?
  local after; after=$(sha256sum "$wd/km_global_hisnr.star" | cut -d' ' -f1)
  local movie_sha; movie_sha=$(sha256sum "$wd/km_global_hisnr.mrcs" 2>/dev/null | cut -d' ' -f1)
  python3 "$tree/tools/verify_fixtures.py" --fixtures-dir "$wd" \
      --manifest "$tree/test-data/known_motion/MANIFEST.json" --cases km_global_hisnr \
      > "$wd/verify.log" 2>&1
  local ver_rc=$?
  # A nonzero exit is NOT evidence of detection on its own -- it can come from a missing
  # artifact or an unrelated error. Attribute it to a named check.
  local why="none"
  grep -q "STAR disagreement"        "$wd/gen.log"    2>/dev/null && why="generator STAR check"
  grep -q "generated movie sha256"   "$wd/gen.log"    2>/dev/null && why="generator MOVIE digest"
  grep -q "STAR input hash MISMATCH" "$wd/verify.log" 2>/dev/null && why="verifier STAR digest"
  echo "  [$label]"
  echo "    generator --canonical exit   : $gen_rc"
  echo "    committed STAR rewritten     : $([ "$before" = "$after" ] && echo NO || echo "YES  ->$(echo $after|cut -c1-16)")"
  echo "    voltage now in the STAR      : $(grep -oE ' [0-9]{3}\.[0-9] ' "$wd/km_global_hisnr.star" | head -1 | tr -d ' ')"
  echo "    generated movie sha256       : $(echo ${movie_sha:-none} | cut -c1-16)  ($([ "${movie_sha:-x}" = "$CANON_MOVIE_SHA" ] && echo 'EQUALS canonical -- movie digest is blind to this mutation' || echo 'differs from canonical'))"
  echo "    verify_fixtures exit         : $ver_rc"
  echo "    what actually rejected it    : $why"
  echo "    verdict                      : $([ "$why" = "none" ] && echo 'NOT DETECTED -- gates would run on mutated optics' || echo 'DETECTED')"
}
run_arm "reviewed_head_$PREV" "$OLD"
run_arm "fix_head" "$ROOT/src"

echo; echo "##### NEGATIVE CONTROL: final-head tests vs BASE main source #####"
NC=$ROOT/ncsrc; rm -rf "$NC"
git -C "$ROOT/src" worktree add -q --detach "$NC" "$BASE"
cd "$NC"
git checkout -q "$HEAD_SHA" -- tests tools CMakeLists.txt test-data .github
# Commit the candidate tooling onto the detached base HEAD.
#
# verify_fixtures.py deliberately reads the manifest from git:HEAD, not from the
# working tree, so that a generator-adjacent overwrite cannot self-certify. In a
# throwaway worktree that is detached at BASE, git:HEAD therefore still resolves
# to BASE's MANIFEST.json -- which predates star_sha256 -- and Control 6 fails on
# a schema rejection that is an artifact of this harness rather than a defect in
# the candidate. Committing makes git:HEAD agree with the working tree, so the
# only failures left are genuine src/ defects.
git -c user.name=i96-negative-control -c user.email=noreply@localhost \
    commit -q -m "negative control: base src/ with candidate tooling" || true
echo "nc HEAD now carries candidate tooling: MANIFEST has star_sha256 = $(git show HEAD:test-data/known_motion/MANIFEST.json | grep -c star_sha256) entries"
echo "nc src/ is still base: image.h $( [ "$(sha256sum < src/image.h)" = "$(git show $BASE:src/image.h | sha256sum)" ] && echo yes || echo NO ), motioncorr_runner.cpp $( [ "$(sha256sum < src/motioncorr_runner.cpp)" = "$(git show $BASE:src/motioncorr_runner.cpp | sha256sum)" ] && echo yes || echo NO )"
cmake -S "$NC" -B "$NC/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF \
      -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/nc-cfg.log" 2>&1
echo "nc configure exit=$?"
cmake --build "$NC/build" --parallel $J > "$LOG/nc-build.log" 2>&1
echo "nc build exit=$?  (a control that does not build detects nothing)"
( cd "$NC/build" && OMP_NUM_THREADS=$J ctest --output-on-failure -j4 > "$LOG/nc-ctest.log" 2>&1; echo "nc ctest exit=$?" )
grep -E "tests passed|tests failed" "$LOG/nc-ctest.log"
echo "tests failing on base source (must still be exactly the four integrated groups'):"
sed -n "/The following tests FAILED/,\$p" "$LOG/nc-ctest.log"

echo; echo "##### DONE #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
echo "No GPU build, run or queuing performed by this job."
