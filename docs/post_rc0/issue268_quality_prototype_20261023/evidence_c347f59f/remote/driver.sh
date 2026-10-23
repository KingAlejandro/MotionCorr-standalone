#!/bin/bash
# #268 quality-report prototype: remote CPU-only evidence driver (PROTOCOL.md).
# One pass, no retries. Every step writes a receipt; any failure stops the driver.
set -u -o pipefail
S="$1"            # fresh scratch directory (already created, contains q268.bundle)
EXP=c347f59f25a2148642130136c6462491c8db36d1
BASE=bbf24607dec537bd13351f061047ea38bd38237b
C1REPO=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src
PY=/home/alex/.mc-venv/bin/python3
NVCC=/usr/local/cuda-12.8/bin/nvcc
R="$S/receipts"; mkdir -p "$R"
step() { echo "$(date -u +%FT%TZ) $*" | tee -a "$R/steps.log"; }
fail() { step "STOP: $*"; echo "$1" > "$R/stop_reason"; exit 2; }

step "driver pid $$ start host $(hostname)"
# Dedicated CPU lease for cores 14-15, held for the whole driver.
exec 9>/tmp/motioncorr-q268-cpu14-15.lock
flock -n 9 || fail "cpu14-15 lease contended"
for f in /tmp/motioncorr-guard264-cpu14-15.lock /tmp/motioncorr-i61-cpu-14-15.lock; do
  i=$(stat -c %i "$f"); n=$(grep -c ":$i " /proc/locks || true)
  echo "$f held=$n" >> "$R/admission.txt"
  [ "$n" = 0 ] || fail "lane lock $f held"
done
for p in 3315461 3315463; do [ -e /proc/$p ] && fail "guard pid $p live"; echo "guard $p absent" >> "$R/admission.txt"; done
taskset -pc $$ >> "$R/admission.txt"
df -h /mnt/clathrin >> "$R/admission.txt"

step "repo"
git init -q "$S/repo" || fail "git init"
git -C "$S/repo" fetch -q "$C1REPO" HEAD 2>"$R/fetch_c1.err" || fail "fetch c1"
git -C "$S/repo" fetch -q "$S/q268.bundle" "refs/heads/*:refs/heads/*" 2>"$R/fetch_bundle.err" || fail "fetch bundle"
git -C "$S/repo" worktree add -q --detach "$S/src-base" "$BASE" || fail "worktree base"
git -C "$S/repo" worktree add -q --detach "$S/src-exp" "$EXP" || fail "worktree exp"
{ for d in src-base src-exp; do echo "$d commit $(git -C $S/$d rev-parse HEAD) tree $(git -C $S/$d rev-parse HEAD^{tree}) status [$(git -C $S/$d status --porcelain | wc -l)]"; done; } > "$R/sources.txt"
[ "$(git -C $S/src-exp rev-parse HEAD)" = "$EXP" ] || fail "exp sha"
[ "$(git -C $S/src-base rev-parse HEAD)" = "$BASE" ] || fail "base sha"
git -C "$S/repo" diff --stat "$BASE" "$EXP" -- src CMakeLists.txt > "$R/source_diff_stat.txt"

step "fixtures"
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 taskset -c 14 "$PY" -B "$S/src-exp/test-data/generate_motion_diagnostics.py" --outdir "$S/fixtures" > "$R/fixtures.log" 2>&1 || fail "fixtures"

build() {  # name src cmake-args...
  local name=$1 src=$2; shift 2
  step "configure $name"
  taskset -c 14-15 cmake -S "$S/$src" -B "$S/build-$name" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$PY" "$@" > "$R/configure-$name.log" 2>&1 \
    || fail "configure $name"
  step "build $name"
  flock -n -E 75 /tmp/motioncorr-build.lock taskset -c 14-15 cmake --build "$S/build-$name" --target motioncorr -j2 > "$R/build-$name.log" 2>&1
  local rc=$?
  echo "$name build rc=$rc" >> "$R/builds.txt"
  [ $rc = 0 ] || fail "build $name rc=$rc (75 = shared build lock held)"
  sha256sum "$S/build-$name/motioncorr" >> "$R/binaries.txt"
}
build b0 src-base
build b1 src-exp
build b2 src-exp -DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON
grep -E "CMAKE_CXX_COMPILER:|CMAKE_CXX_FLAGS_RELEASE:|MOTIONCORR_EXPERIMENTAL_QUALITY_REPORT|CUDA:BOOL" "$S"/build-b*/CMakeCache.txt > "$R/build_options.txt"
"$S/build-b0/motioncorr" --experimental_quality_report > "$R/b0_flag_probe.txt" 2>&1; echo "b0 flag probe rc=$?" >> "$R/b0_flag_probe.txt"
"$S/build-b1/motioncorr" --experimental_quality_report > "$R/b1_flag_probe.txt" 2>&1; echo "b1 flag probe rc=$?" >> "$R/b1_flag_probe.txt"

step "checker selftest"
taskset -c 14 "$PY" -B "$S/src-exp/docs/post_rc0/issue268_quality_prototype_20261023/quality_controls.py" selftest > "$R/selftest.log" 2>&1 || fail "selftest"

step "campaign"
taskset -c 14 "$PY" -B "$S/src-exp/docs/post_rc0/issue268_quality_prototype_20261023/quality_controls.py" campaign \
  --fixtures "$S/fixtures" --root "$S/campaign" --b0 "$S/build-b0/motioncorr" --b1 "$S/build-b1/motioncorr" \
  --b2 "$S/build-b2/motioncorr" --cpu 14 > "$R/campaign.log" 2>&1
echo "campaign rc=$?" >> "$R/campaign.log"

step "cuda compile-only b3"
taskset -c 14-15 cmake -S "$S/src-exp" -B "$S/build-b3" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$PY" \
  -DCUDA=ON -DCMAKE_CUDA_COMPILER="$NVCC" -DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON > "$R/configure-b3.log" 2>&1 || fail "configure b3"
flock -n -E 75 /tmp/motioncorr-build.lock taskset -c 14-15 cmake --build "$S/build-b3" --target motioncorr -j2 > "$R/build-b3.log" 2>&1
echo "b3 build rc=$?" >> "$R/builds.txt"
[ -f "$S/build-b3/motioncorr" ] && sha256sum "$S/build-b3/motioncorr" >> "$R/binaries.txt"

du -sh "$S" > "$R/scratch_usage.txt"
step "driver done"
echo 0 > "$R/driver_exit"
