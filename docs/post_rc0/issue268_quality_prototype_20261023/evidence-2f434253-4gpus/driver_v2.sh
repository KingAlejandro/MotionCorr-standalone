#!/bin/bash
# #268 quality-report prototype v2: remote CPU-only evidence driver (PROTOCOL_V2.md).
# One pass, no retries. Every step writes a receipt; any admission/build failure stops.
set -u -o pipefail
S="$1"
HEAD=2f43425340b7525e85288e7b35ee109dd3a4c3cc
BASE=bbf24607dec537bd13351f061047ea38bd38237b
C1REPO=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src
PY=/home/alex/.mc-venv/bin/python3
NVCC=/usr/local/cuda-12.8/bin/nvcc
R="$S/receipts"; mkdir -p "$R" "$S/tmp"
export TMPDIR="$S/tmp"
step() { echo "$(date -u +%FT%TZ) $*" | tee -a "$R/steps.log"; }
fail() { step "STOP: $*"; echo "$1" > "$R/stop_reason"; exit 2; }

step "driver pid $$ start host $(hostname)"
exec 9>/tmp/motioncorr-q268v2-cpu14-15.lock
flock -n 9 || fail "q268v2 cpu14-15 lease contended"
for f in /tmp/motioncorr-q268-cpu14-15.lock /tmp/motioncorr-guard264-cpu14-15.lock /tmp/motioncorr-i61-cpu-14-15.lock; do
  i=$(stat -c %i "$f"); n=$(grep -c ":$i " /proc/locks || true)
  echo "$f inode=$i held=$n" >> "$R/admission.txt"
  [ "$n" = 0 ] || fail "lock $f held"
done
for p in 3315461 3315463 3324419; do [ -e /proc/$p ] && fail "old pid $p live"; echo "old pid $p absent" >> "$R/admission.txt"; done
others=$(pgrep -af 'q268' | grep -v "$$" | grep -v 'driver_v2.sh' | grep -v pgrep || true)
echo "other q268 processes: [$others]" >> "$R/admission.txt"
[ -z "$others" ] || fail "other q268 processes present"
ps -eLo pid,psr,stat,comm | awk '($2==14||$2==15) && $3 ~ /R/' > "$R/cpu14_15_running_at_admission.txt"
taskset -pc $$ >> "$R/admission.txt"
df -h /mnt/clathrin >> "$R/admission.txt"

step "repo"
git init -q "$S/repo" || fail "git init"
git -C "$S/repo" fetch -q "$C1REPO" HEAD 2>"$R/fetch_c1.err" || fail "fetch c1"
git -C "$S/repo" fetch -q "$S/q268v2.bundle" "refs/heads/*:refs/heads/*" 2>"$R/fetch_bundle.err" || fail "fetch bundle"
git -C "$S/repo" worktree add -q --detach "$S/src-base" "$BASE" || fail "worktree base"
git -C "$S/repo" worktree add -q --detach "$S/src-exp" "$HEAD" || fail "worktree exp"
{ for d in src-base src-exp; do echo "$d commit $(git -C $S/$d rev-parse HEAD) tree $(git -C $S/$d rev-parse HEAD^{tree}) status [$(git -C $S/$d status --porcelain | wc -l)]"; done; } > "$R/sources.txt"
[ "$(git -C $S/src-exp rev-parse HEAD)" = "$HEAD" ] || fail "head sha"
[ "$(git -C $S/src-base rev-parse HEAD)" = "$BASE" ] || fail "base sha"
git -C "$S/repo" diff --stat "$BASE" "$HEAD" -- src CMakeLists.txt > "$R/source_diff_stat.txt"
git -C "$S/repo" diff --stat 1215febd526c4e4499d75c67cd888192153bcc3c "$HEAD" -- src CMakeLists.txt > "$R/source_diff_vs_1215febd.txt"

step "fixtures"
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 taskset -c 14 "$PY" -B "$S/src-exp/test-data/generate_motion_diagnostics.py" --outdir "$S/fixtures" > "$R/fixtures.log" 2>&1 || fail "fixtures"

build() {  # name src target cmake-args...
  local name=$1 src=$2 target=$3; shift 3
  step "configure $name"
  taskset -c 14-15 cmake -S "$S/$src" -B "$S/build-$name" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$PY" "$@" > "$R/configure-$name.log" 2>&1 \
    || fail "configure $name"
  step "build $name ($target)"
  flock -n -E 75 /tmp/motioncorr-build.lock taskset -c 14-15 cmake --build "$S/build-$name" --target "$target" -j2 > "$R/build-$name.log" 2>&1
  local rc=$?
  echo "$name target=$target build rc=$rc" >> "$R/builds.txt"
  return $rc
}
build v0 src-base motioncorr || fail "build v0 (75 = shared build lock held)"
build v1 src-exp all || fail "build v1 (75 = shared build lock held)"
build v2 src-exp all -DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON || fail "build v2 (75 = shared build lock held)"
sha256sum "$S"/build-v0/motioncorr "$S"/build-v1/motioncorr "$S"/build-v2/motioncorr "$S"/build-v2/quality_report_unit >> "$R/binaries.txt"
grep -E "CMAKE_CXX_COMPILER:|CMAKE_CXX_FLAGS_RELEASE:|MOTIONCORR_EXPERIMENTAL_QUALITY_REPORT|CUDA:BOOL" "$S"/build-v*/CMakeCache.txt > "$R/build_options.txt"
for b in v0 v1 v2; do echo "$b flag_string=$(grep -c -a -- '--experimental_quality_report' $S/build-$b/motioncorr) mcquality_symbols=$(nm -C $S/build-$b/motioncorr | grep -c 'mcquality::')"; done > "$R/static_flag_witness.txt"
echo "command: grep -c -a -- '--experimental_quality_report' BIN; nm -C BIN | grep -c 'mcquality::'" >> "$R/static_flag_witness.txt"

step "campaign"
taskset -c 14 "$PY" -B "$S/src-exp/docs/post_rc0/issue268_quality_prototype_20261023/quality_controls_v2.py" campaign \
  --fixtures "$S/fixtures" --root "$S/campaign" --v0 "$S/build-v0/motioncorr" --v1 "$S/build-v1/motioncorr" \
  --v2 "$S/build-v2/motioncorr" --revision "$HEAD" --cpu 14 > "$R/campaign.log" 2>&1
echo "campaign rc=$?" >> "$R/campaign.log"
( cd "$S" && find campaign -type f -print0 | sort -z | xargs -0 sha256sum ) > "$R/campaign_files.sha256"

for b in v1 v2; do
  step "ctest $b"
  ( cd "$S/build-$b" && taskset -c 14-15 ctest -N > "$R/ctest-$b-list.txt" 2>&1; \
    taskset -c 14-15 ctest -j1 --output-on-failure > "$R/ctest-$b.log" 2>&1; echo "ctest $b rc=$?" >> "$R/ctest-summary.txt" )
  tail -5 "$R/ctest-$b.log" >> "$R/ctest-summary.txt"
  "$PY" -B "$S/src-exp/tools/validate_test_collection.py" --test-dir "$S/build-$b" > "$R/validate-collection-$b.log" 2>&1
  echo "validate_test_collection $b rc=$?" >> "$R/ctest-summary.txt"
done

for b in v3 v4; do
  extra=""; [ $b = v4 ] && extra="-DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON"
  if build $b src-exp motioncorr -DCUDA=ON -DCMAKE_CUDA_COMPILER="$NVCC" $extra; then
    sha256sum "$S/build-$b/motioncorr" >> "$R/binaries.txt"
  else
    step "cuda compile $b not completed (rc recorded in builds.txt; not retried)"
  fi
done

du -sh "$S" > "$R/scratch_usage.txt"
step "driver done"
echo 0 > "$R/driver_exit"
