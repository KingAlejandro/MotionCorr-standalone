#!/usr/bin/env bash
# round96 correctness-foundation integration -- CPU validation phase 1
# Build + full CTest suite + fail-closed tooling chain + negative controls.
# Lane: cpu64, taskset -c 32-63 (NUMA node1), build/runtime <= 16,
#       serialized under /tmp/motioncorr-issue96-cpu-validation.lock.
set -uo pipefail

ROOT=/home/ubuntu/mc-i96-integration
VENV=/home/ubuntu/.mc-venv
BUNDLE=/home/ubuntu/mc-i96-integration.bundle
CAND=a8b0f1c9   # placeholder, overwritten below
LOG=$ROOT/logs
J=16

rm -rf "$ROOT"
mkdir -p "$ROOT" "$LOG"
exec > >(tee -a "$LOG/phase1.log") 2>&1

echo "##### PROVENANCE #####"
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
echo "host: $(hostname)"; uname -a
echo "--- inherited cpuset (this job) ---"
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
echo "--- numa policy ---"
numactl --show
echo "--- lscpu CPU->NODE/SOCKET/CORE (node1 lane) ---"
lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#' | awk -F, '$1>=32 && $1<=63' | head -40
echo "--- SMT ---"
echo "Thread(s) per core: $(lscpu | awk -F: '/Thread\(s\) per core/{gsub(/ /,"",$2);print $2}')  (1 = no SMT, so each logical CPU is a physical core)"
echo "--- load and interference at start ---"
cat /proc/loadavg
ps -eo pid,user,pcpu,etimes,comm --sort=-pcpu | head -8
for p in $(pgrep -x ctffind); do echo "ctffind pid=$p Cpus_allowed_list=$(awk '/Cpus_allowed_list/{print $2}' /proc/$p/status)"; done
echo "--- toolchain ---"
g++ --version | head -1
$VENV/bin/cmake --version | head -1
$VENV/bin/python3 --version
$VENV/bin/python3 -c "import numpy;print('numpy', numpy.__version__)"
pkg-config --modversion libtiff-4 2>/dev/null | sed 's/^/libtiff-4 /'

echo
echo "##### SOURCE #####"
sha256sum "$BUNDLE"
cd "$ROOT"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" src
cd src
CAND=$(git rev-parse HEAD)
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
echo "candidate head: $CAND"
echo "base (origin/main pin): $BASE"
git log --oneline "$BASE..HEAD" | wc -l | sed 's/^/commits on top of base: /'
echo "--- working tree clean? ---"; git status --porcelain | head
echo "--- source tree hash (git tree object of candidate) ---"
git rev-parse HEAD^{tree}
echo "--- tracked-source digest (src/ tests/ tools/ CMakeLists.txt .github/) ---"
git ls-files src tests tools CMakeLists.txt .github test-data | sort | xargs sha256sum | sha256sum

echo
echo "##### BUILD (Release, BUILD_TESTING=ON, CUDA=OFF) #####"
$VENV/bin/cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF \
    -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/configure.log" 2>&1
echo "configure exit=$?"
tail -5 "$LOG/configure.log"
grep -E "CMAKE_BUILD_TYPE|CMAKE_CXX_FLAGS_RELEASE" build/CMakeCache.txt
$VENV/bin/cmake --build build --parallel $J > "$LOG/build.log" 2>&1
echo "build exit=$?"
grep -ciE "warning" "$LOG/build.log" | sed 's/^/build warnings: /'
echo "--- binary provenance ---"
ls -l build/motioncorr
sha256sum build/motioncorr build/runner_numerics build/image_write_faults 2>/dev/null
echo "--- optimisation actually applied (guard against the -O0 default trap) ---"
grep -m1 -- "-O3" "$LOG/build.log" | head -c 200; echo
strings build/motioncorr | grep -m1 -i "GCC:" || true

echo
echo "##### CTEST: full suite on the combined tree #####"
cd build
OMP_NUM_THREADS=$J $VENV/bin/ctest --output-on-failure -j4 > "$LOG/ctest.log" 2>&1
echo "ctest exit=$?"
tail -25 "$LOG/ctest.log"
echo "--- collected test names ---"
$VENV/bin/ctest --show-only=json-v1 | $VENV/bin/python3 -c "import json,sys;d=json.load(sys.stdin);ns=[t['name'] for t in d['tests']];print(len(ns));[print(' ',n) for n in ns]"
cd "$ROOT/src"

echo
echo "##### FAIL-CLOSED TOOLING CHAIN (#72 order) #####"
run() { echo "--- \$ $*"; "$@"; echo "exit=$?"; }
run $VENV/bin/python3 tools/ci_preflight.py
run $VENV/bin/python3 tools/validate_test_collection.py --test-dir build
run $VENV/bin/python3 test-data/generate_known_motion_fixture.py --canonical
run $VENV/bin/python3 tools/verify_fixtures.py
run $VENV/bin/python3 tools/test_ci_fail_closed.py -v

echo
echo "##### DONE PHASE 1 #####"
date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
