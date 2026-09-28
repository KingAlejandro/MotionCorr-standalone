#!/bin/bash
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-i99f
rm -rf "$R"; mkdir -p "$R"
exec > >(tee "$R/run.log") 2>&1

NEW_SHA=57ba66180e1e9fe64a48551364985d49d2853a1b
OLDT_SHA=fb2fab8e6b91356e796d10f38a7891459b212428
NEG_SHA=2101c3c3a1c1fd1a41b2ac7ad62c48097c4eba41

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
sha256sum "$HOME/mc-i99f.bundle"

stage () {
  local name=$1 sha=$2
  echo "--- stage $name @ $sha ---"
  rm -rf "$R/src-$name"; git init --quiet "$R/src-$name"
  git -C "$R/src-$name" fetch "$HOME/mc-i99f.bundle" '+refs/heads/*:refs/remotes/bundle/*' >/dev/null 2>&1 \
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

run_under () {  # name builddir blocks
  local name=$1 bd=$2 blocks=$3
  echo "----- $name under ulimit -f $blocks -----"
  ( cd "$bd" && taskset -c 32-63 bash -c "
      ulimit -f $blocks || { echo 'ULIMIT FAILED'; exit 90; }
      python3 -c \"
import resource, sys
p = resource.getrlimit(resource.RLIMIT_FSIZE)
print('inherited by ctest:', p)
sys.exit(1 if p[1] == resource.RLIM_INFINITY else 0)
\" || { echo 'CONTROL VOID: hard limit still infinity; nothing was applied'; exit 91; }
      ctest -V -R 'ImageWriteFaults|WriteFaults'" ) > "$R/hl-$name.log" 2>&1
  echo "exit=$?"
  grep -E "CONTROL VOID|ULIMIT FAILED|inherited by ctest|inherited RLIMIT|precheck|setrlimit|SubprocessError|what\\(\\):|phase [0-9]|finite-hard|Passed|[*][*][*]|tests passed|tests failed" "$R/hl-$name.log" | head -28
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
echo "########## 2-3. FINITE HARD RLIMIT_FSIZE: candidate and pre-delta tests ##########"
echo "########## 'ulimit -f N' sets BOTH; 'ulimit -H -f N' leaves soft=infinity and is rejected by the kernel ##########"
run_under candidate-8Mi "$R/src-new/build-cpu"  8192
run_under candidate-4Mi "$R/src-new/build-cpu"  4096
run_under predelta-8Mi  "$R/src-oldt/build-cpu" 8192
echo "----- predelta with NO finite hard limit (isolates the cause) -----"
( cd "$R/src-oldt/build-cpu" && taskset -c 32-63 ctest -R "ImageWriteFaults|WriteFaults" ) > "$R/hl-predelta-nolimit.log" 2>&1
echo "exit=$?"; grep -E "tests passed|tests failed" "$R/hl-predelta-nolimit.log"

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

echo
echo "########## 7. VACUITY GUARD: stray MC_WRITE_FAULTS_IN_CHILD with no finite hard limit ##########"
echo "########## must FAIL rather than print a control it never ran ##########"
cd "$R/src-new/build-cpu"
taskset -c 32-63 env MC_WRITE_FAULTS_IN_CHILD=1 ./image_write_faults > "$R/vacuity.log" 2>&1
echo "exit=$? (nonzero expected)"; cat "$R/vacuity.log"

echo "### load at end:"; uptime
echo "### done"; date -Is
}

echo "### acquiring /tmp/motioncorr-issue96-cpu-validation.lock"
flock /tmp/motioncorr-issue96-cpu-validation.lock bash -c "
  R=$R; NEW_SHA=$NEW_SHA; OLDT_SHA=$OLDT_SHA; NEG_SHA=$NEG_SHA
  $(declare -f stage); $(declare -f build); $(declare -f run_under); $(declare -f body); body
"
echo "=== ALL DONE rc=$? ==="; date -Is
