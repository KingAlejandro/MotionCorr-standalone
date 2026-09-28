#!/bin/bash
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-i99
rm -rf "$R"; mkdir -p "$R"
exec > >(tee "$R/run.log") 2>&1

HEAD_SHA=239320f61c43576ebff97e378ab1cc0835ce8eae   # fix + tests
NEG_SHA=39220eac57ecb4b0228d5e3f9152d7984363b045    # base 4c952b3 + tests ONLY (must fail)

echo "=== provenance ==="
date -Is; hostname; nproc; uptime
grep Cpus_allowed_list /proc/self/status
sha256sum "$HOME/mc-i99.bundle"
cmake --version | head -1; g++ --version | head -1; python3 --version
echo "filesystem for TMPDIR:"; df -T /tmp | tail -2

stage () {
  local name=$1 sha=$2
  echo "--- stage $name @ $sha ---"
  rm -rf "$R/src-$name"
  git init --quiet "$R/src-$name"
  git -C "$R/src-$name" fetch "$HOME/mc-i99.bundle" \
      '+refs/heads/*:refs/remotes/bundle/*' '+refs/remotes/origin/*:refs/remotes/base/*' >/dev/null 2>&1 \
    || { echo "FETCH FAILED $name"; return 1; }
  git -C "$R/src-$name" checkout --quiet --detach "$sha" || { echo "CHECKOUT FAILED $name"; return 1; }
  local got; got=$(git -C "$R/src-$name" rev-parse HEAD)
  echo "HEAD=$got expected=$sha"
  [ "$got" = "$sha" ] || { echo "HEAD MISMATCH $name"; return 1; }
  echo "TREE=$(git -C "$R/src-$name" rev-parse 'HEAD^{tree}')"
  echo "STATUS: $(git -C "$R/src-$name" status --porcelain | wc -l) modified files (must be 0)"
  echo "SOURCE HASHES:"
  (cd "$R/src-$name" && sha256sum src/rwMRC.h src/image.h src/micrograph_model.cpp \
      tests/test_image_write_faults.cpp tests/test_write_faults.py CMakeLists.txt \
      test-data/synthetic/synthetic_movie.tiff)
}

build () {
  local name=$1
  echo "=== build $name (Release, CUDA=OFF, BUILD_TESTING=ON, j16, taskset 32-63) ==="
  cd "$R/src-$name" || return 1
  taskset -c 32-63 cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
      -DBUILD_TESTING=ON > "$R/configure-$name.log" 2>&1 \
    || { echo "CONFIGURE FAILED $name"; tail -30 "$R/configure-$name.log"; return 1; }
  grep -E '^CMAKE_BUILD_TYPE|^CMAKE_CXX_FLAGS_RELEASE' build-cpu/CMakeCache.txt
  taskset -c 32-63 cmake --build build-cpu --parallel 16 > "$R/build-$name.log" 2>&1 \
    || { echo "BUILD FAILED $name"; tail -40 "$R/build-$name.log"; return 1; }
  echo "build $name OK"
  sha256sum build-cpu/motioncorr build-cpu/image_write_faults
}

run_ctest () {
  local name=$1 args=${2:-}
  echo "=== ctest $name ${args} ==="
  cd "$R/src-$name/build-cpu" || return 1
  taskset -c 32-63 ctest --output-on-failure -j 4 $args > "$R/ctest-$name.log" 2>&1
  echo "ctest $name exit=$?"
  grep -E '^\s+[0-9]+/[0-9]+ Test|tests passed|tests failed' "$R/ctest-$name.log" | tail -30
}

body () {
  echo '### lock acquired'; date -Is

  # ---------- candidate: fix + tests ----------
  stage head "$HEAD_SHA" && build head && run_ctest head

  # ---------- negative control: base + tests only, MUST FAIL ----------
  echo
  echo "=== NEGATIVE CONTROL: pre-fix main 4c952b3 with the new tests only ==="
  echo "=== these two tests MUST fail here, or they do not detect the defect ==="
  stage neg "$NEG_SHA" && build neg
  cd "$R/src-neg/build-cpu" || return 1
  taskset -c 32-63 ctest --output-on-failure -R 'ImageWriteFaults|WriteFaults' \
      > "$R/ctest-neg.log" 2>&1
  echo "negative-control ctest exit=$? (nonzero is the expected result)"
  tail -60 "$R/ctest-neg.log"

  # ---------- healthy byte parity between base and candidate ----------
  echo
  echo "=== healthy-output byte parity: pre-fix vs post-fix, same input ==="
  W=$R/parity; rm -rf "$W"; mkdir -p "$W/mov" "$W/out-neg" "$W/out-head"
  cp "$R/src-head/test-data/synthetic/synthetic_movie.tiff" "$W/mov/p.tiff"
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
  for arm in neg head; do
    ( cd "$W" && taskset -c 32-63 "$R/src-$arm/build-cpu/motioncorr" --i p.star \
        --o "out-$arm/" --use_own --j 2 --skip_defect --angpix 1.0 --voltage 300 \
        --patch_x 1 --patch_y 1 --bfactor 150 --skip_logfile > "$W/run-$arm.log" 2>&1 )
    echo "arm $arm exit=$?"
  done
  echo "--- produced files ---"
  ( cd "$W" && find out-neg out-head -type f | sort | xargs ls -l )
  echo "--- MRC payload hashes (skip the 1024-byte header: it carries a timestamp) ---"
  for arm in neg head; do
    echo -n "$arm mov/p.mrc payload: "
    tail -c +1025 "$W/out-$arm/mov/p.mrc" | sha256sum
    echo -n "$arm mov/p.mrc whole:   "; sha256sum "$W/out-$arm/mov/p.mrc" | cut -d' ' -f1
    echo -n "$arm mov/p.mrc bytes:   "; stat -c %s "$W/out-$arm/mov/p.mrc"
  done
  echo "--- header field diff (bytes 0..1023, excluding the 80-char label at 224) ---"
  cmp -l <(head -c 224 "$W/out-neg/mov/p.mrc") <(head -c 224 "$W/out-head/mov/p.mrc") \
    && echo "first 224 header bytes identical"
  echo "--- per-movie STAR diff ---"
  diff "$W/out-neg/mov/p.star" "$W/out-head/mov/p.star" && echo "per-movie STAR identical"
  echo "--- joint STAR diff ---"
  diff "$W/out-neg/corrected_micrographs.star" "$W/out-head/corrected_micrographs.star" \
    && echo "joint STAR identical"

  echo '### done'; date -Is
}

echo "### acquiring /tmp/motioncorr-issue96-cpu-validation.lock"
flock /tmp/motioncorr-issue96-cpu-validation.lock bash -c "
  R=$R; HEAD_SHA=$HEAD_SHA; NEG_SHA=$NEG_SHA
  $(declare -f stage); $(declare -f build); $(declare -f run_ctest); $(declare -f body)
  body
"
echo "=== ALL DONE rc=$? ==="
date -Is
