#!/bin/bash
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-i99r2
rm -rf "$R"; mkdir -p "$R"
exec > >(tee "$R/run.log") 2>&1

NEW_SHA=10842690b48aacdcd1c6404ba021ad8ce7676e5d   # fixed writer + fixed tests
OLDT_SHA=33dee9e25568bb64bcfff018a9b79bf66b77a28c  # fixed writer + PRE-delta tests
NEG_SHA=28727aa1eab62b6f34417ec465785cc4b3a65455   # pre-fix main + fixed tests

echo "=== provenance: host, payload, cpuset, NUMA, memory policy, load ==="
date -Is; hostname; uname -r
echo "-- nproc/online:"; nproc; nproc --all; cat /sys/devices/system/cpu/online
echo "-- load at start:"; uptime; cat /proc/loadavg
echo "-- cpuset inherited by this shell:"; grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/self/status
echo "-- cgroup:"; cat /proc/self/cgroup | head -3
echo "-- NUMA topology:"; (numactl --hardware 2>/dev/null || echo "numactl unavailable") | head -12
echo "-- memory policy of this shell:"; (numactl --show 2>/dev/null || echo "numactl unavailable")
echo "-- meminfo:"; grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree)' /proc/meminfo
echo "-- RLIMIT_FSIZE of this shell (the harness's own inherited pair):"
python3 -c "import resource;print(resource.getrlimit(resource.RLIMIT_FSIZE))"
echo "-- filesystem:"; df -T /tmp "$HOME" | tail -3
echo "-- heaviest processes right now:"; ps -eo user,pid,pcpu,pmem,comm --sort=-pcpu | head -6
echo "-- toolchain:"; cmake --version|head -1; g++ --version|head -1; python3 --version
sha256sum "$HOME/mc-i99r2.bundle"

stage () {
  local name=$1 sha=$2
  echo "--- stage $name @ $sha ---"
  rm -rf "$R/src-$name"; git init --quiet "$R/src-$name"
  git -C "$R/src-$name" fetch "$HOME/mc-i99r2.bundle" '+refs/heads/*:refs/remotes/bundle/*' >/dev/null 2>&1 \
    || { echo "FETCH FAILED $name"; return 1; }
  git -C "$R/src-$name" checkout --quiet --detach "$sha" || { echo "CHECKOUT FAILED $name"; return 1; }
  local got; got=$(git -C "$R/src-$name" rev-parse HEAD)
  echo "HEAD=$got expected=$sha"; [ "$got" = "$sha" ] || { echo "HEAD MISMATCH $name"; return 1; }
  echo "TREE=$(git -C "$R/src-$name" rev-parse 'HEAD^{tree}')"
  echo "STATUS: $(git -C "$R/src-$name" status --porcelain | wc -l) modified files (must be 0)"
  (cd "$R/src-$name" && sha256sum src/rwMRC.h src/image.h src/micrograph_model.cpp \
      tests/test_image_write_faults.cpp tests/test_write_faults.py)
}

build () {
  local name=$1
  echo "=== build $name (Release, CUDA=OFF, BUILD_TESTING=ON, j16, taskset 32-63) ==="
  cd "$R/src-$name" || return 1
  taskset -c 32-63 cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
      -DBUILD_TESTING=ON > "$R/configure-$name.log" 2>&1 \
    || { echo "CONFIGURE FAILED $name"; tail -20 "$R/configure-$name.log"; return 1; }
  grep -E '^CMAKE_BUILD_TYPE|^CMAKE_CXX_FLAGS_RELEASE' build-cpu/CMakeCache.txt
  taskset -c 32-63 cmake --build build-cpu --parallel 16 > "$R/build-$name.log" 2>&1 \
    || { echo "BUILD FAILED $name"; tail -25 "$R/build-$name.log"; return 1; }
  echo "build $name OK"; sha256sum build-cpu/motioncorr build-cpu/image_write_faults
  echo "-- payload cpuset witness (build ran under):"
  taskset -c 32-63 grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/self/status
}

body () {
echo "### lock acquired"; date -Is

stage new  "$NEW_SHA" && build new  || { echo "CANDIDATE BUILD FAILED"; return 1; }
stage oldt "$OLDT_SHA" && build oldt || { echo "HARNESS-CONTROL BUILD FAILED"; return 1; }
stage neg  "$NEG_SHA"  && build neg  || { echo "NEGATIVE CONTROL BUILD FAILED -- invalid, not passing"; return 1; }

echo
echo "########## 1. CANDIDATE: full CPU CTest, normal environment ##########"
cd "$R/src-new/build-cpu"
taskset -c 32-63 ctest --output-on-failure -j 4 > "$R/ctest-new.log" 2>&1
echo "exit=$?"; grep -E 'Test +#|tests passed|tests failed' "$R/ctest-new.log" | tail -20

echo
echo "########## 2. CANDIDATE: the two fault tests under a FINITE hard RLIMIT_FSIZE ##########"
echo "(ulimit -H -f 8192 => hard limit 8388608 bytes, lowered irreversibly, unprivileged)"
cd "$R/src-new/build-cpu"
taskset -c 32-63 bash -c 'ulimit -H -f 8192; echo "shell RLIMIT_FSIZE: $(python3 -c "import resource;print(resource.getrlimit(resource.RLIMIT_FSIZE))")"; ctest -V -R "ImageWriteFaults|WriteFaults"' > "$R/ctest-new-hardlimit.log" 2>&1
echo "exit=$?"
grep -E 'shell RLIMIT|^1[0-9]*:|Passed|Failed|tests passed|tests failed' "$R/ctest-new-hardlimit.log" | tail -30

echo
echo "########## 3. HARNESS CONTROL: PRE-DELTA tests, same fixed writer, same finite hard limit ##########"
echo "########## these MUST fail, and must fail at the rlimit plumbing, not at a writer assertion ##########"
cd "$R/src-oldt/build-cpu"
taskset -c 32-63 bash -c 'ulimit -H -f 8192; ctest -V -R "ImageWriteFaults|WriteFaults"' > "$R/ctest-oldt-hardlimit.log" 2>&1
echo "exit=$? (nonzero is the expected result)"
grep -E 'setrlimit|ValueError|OSError|Traceback|preexec|unexpected exception|Passed|Failed|tests passed|tests failed' "$R/ctest-oldt-hardlimit.log" | head -25
echo "-- and the same PRE-DELTA tests WITHOUT the finite hard limit (must pass: isolates the cause) --"
taskset -c 32-63 ctest -R "ImageWriteFaults|WriteFaults" > "$R/ctest-oldt-nolimit.log" 2>&1
echo "exit=$? (zero expected)"; grep -E 'tests passed|tests failed' "$R/ctest-oldt-nolimit.log"

echo
echo "########## 4. NEGATIVE CONTROL: pre-fix main + the new tests (writer defect must still be detected) ##########"
cd "$R/src-neg/build-cpu"
taskset -c 32-63 ctest --output-on-failure -R "ImageWriteFaults|WriteFaults" > "$R/ctest-neg.log" 2>&1
echo "exit=$? (nonzero expected)"
grep -E 'FAIL:|AssertionError|terminate|Not Run|Passed|Failed|tests passed|tests failed' "$R/ctest-neg.log" | head -20

echo
echo "########## 5. HEALTHY BYTE PARITY unchanged by this delta ##########"
W=$R/parity; rm -rf "$W"; mkdir -p "$W/mov" "$W/out"
cp "$R/src-new/test-data/synthetic/synthetic_movie.tiff" "$W/mov/p.tiff"
sha256sum "$W/mov/p.tiff"
cat > "$W/p.star" <<'EOF'
# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.000 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
mov/p.tiff 1
EOF
( cd "$W" && taskset -c 32-63 "$R/src-new/build-cpu/motioncorr" --i p.star --o out/ \
   --use_own --j 2 --skip_defect --angpix 1.0 --voltage 300 --patch_x 1 --patch_y 1 \
   --bfactor 150 --skip_logfile > run.log 2>&1 ); echo "healthy run exit=$?"
echo -n "mov/p.mrc payload sha256: "; tail -c +1025 "$W/out/mov/p.mrc" | sha256sum
echo -n "mov/p.mrc bytes: "; stat -c %s "$W/out/mov/p.mrc"
echo "(expected payload 1a424122f6fd8f9b691197f92d9a6ca712458e9f51898e34232ad3ad271ce9d3, 1049600 bytes)"

echo "### load at end:"; uptime
echo "### done"; date -Is
}

echo "### acquiring /tmp/motioncorr-issue96-cpu-validation.lock"
flock /tmp/motioncorr-issue96-cpu-validation.lock bash -c "
  R=$R; NEW_SHA=$NEW_SHA; OLDT_SHA=$OLDT_SHA; NEG_SHA=$NEG_SHA
  $(declare -f stage); $(declare -f build); $(declare -f body); body
"
echo "=== ALL DONE rc=$? ==="; date -Is
