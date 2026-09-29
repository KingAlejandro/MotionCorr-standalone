#!/usr/bin/env bash
# Issue #85 lane C: inject recoverable and fatal failures at the U16 staging path.
#
# This is deliberately not a default CTest: it needs a native CUDA device and the
# exact unsigned-16 TIFF fixture. It uses the test-only motioncorr_faultinject
# executable; production src/ has no environment-controlled fault path.
#
# Usage:
#   run_u16_failure_controls.sh <faultinject-bin> <movie.tiff>
#       <stage-bytes> <comparator.py> [workdir]
#
# The work directory must be new. It is retained with every log and output tree.
set -euo pipefail

FAULT_BIN=$(realpath "$1")
MOVIE=$(realpath "$2")
STAGE_BYTES=$3
COMPARATOR=$(realpath "$4")
DATA_ROOT=$(cd "$(dirname "$MOVIE")/.." && pwd)
case "$MOVIE" in
    "$DATA_ROOT"/*) MOVIE_REL=${MOVIE#"$DATA_ROOT"/} ;;
    *) echo "FAIL movie must be inside the dataset Movies directory: $MOVIE"; exit 2 ;;
esac
[ "$(dirname "$MOVIE_REL")" = "Movies" ] || {
    echo "FAIL movie must be directly inside the dataset Movies directory: $MOVIE"; exit 2;
}
if [ "${5:-}" != "" ]; then
    WORK=$5
    mkdir "$WORK" 2>/dev/null || { echo "FAIL workdir already exists: $WORK"; exit 2; }
else
    WORK=$(mktemp -d "${TMPDIR:-/tmp}/mc-u16-faults.XXXXXX")
fi

[ -x "$FAULT_BIN" ] || { echo "FAIL missing executable $FAULT_BIN"; exit 2; }
[ -f "$MOVIE" ] || { echo "FAIL missing movie $MOVIE"; exit 2; }
[ -f "$COMPARATOR" ] || { echo "FAIL missing comparator $COMPARATOR"; exit 2; }
case "$STAGE_BYTES" in ''|*[!0-9]*) echo "FAIL stage-bytes must be an integer"; exit 2;; esac
mkdir -p "$WORK/healthy/out"
python3 - "$MOVIE_REL" "$WORK/one_movie_manifest.json" <<'PY'
import json, sys
from pathlib import Path
movie, output = sys.argv[1:]
Path(output).write_text(json.dumps({
    "schema_version": 1,
    "movies": [movie],
    "expected_shape_xyz": [3710, 3838, 1],
    "joint_star": "corrected_micrographs.star",
}, indent=2) + "\n")
PY
MANIFEST="$WORK/one_movie_manifest.json"

COMMON=(--i "$MOVIE_REL" --j 4 --use_own --patch_x 3 --patch_y 3 --bfactor 150
        --dose_weighting --dose_per_frame 1.0 --voltage 200 --angpix 0.885
        --max_iter 1)

count_markers() {
    { grep -R -h -F "$1" "$2" --binary-files=without-match 2>/dev/null || true; } \
        | wc -l | tr -d ' '
}

echo "workdir=$WORK"
echo "movie=$MOVIE"
echo "stage_bytes=$STAGE_BYTES"
echo "=== healthy resident CUDA reference ==="
MC_U16_FAULT=none MC_U16_STAGE_BYTES="$STAGE_BYTES" \
    "$FAULT_BIN" "${COMMON[@]}" --gpu 0 --o "$WORK/healthy/out/" \
    >"$WORK/healthy/out/run.log" 2>&1
[ "$(find "$WORK/healthy/out" -name '*.mrc' -type f | wc -l | tr -d ' ')" = 1 ] || {
    echo "FAIL healthy reference did not produce exactly one corrected MRC"; exit 1;
}
[ "$(find "$WORK/healthy/out" -name corrected_micrographs.star -type f | wc -l | tr -d ' ')" = 1 ] || {
    echo "FAIL healthy reference did not produce the joint STAR"; exit 1;
}
if [ "$(count_markers 'Released native uint16 host staging after device forward FFT.' "$WORK/healthy/out")" -lt 1 ]; then
    echo "FAIL healthy reference did not witness host staging lifetime transition"; exit 1;
fi

run_u16() {
    local mode=$1 out=$2
    mkdir -p "$out"
    set +e
    MC_U16_FAULT="$mode" MC_U16_STAGE_BYTES="$STAGE_BYTES" \
        "$FAULT_BIN" "${COMMON[@]}" --gpu 0 --o "$out/" >"$out/run.log" 2>&1
    local rc=$?
    set -e
    printf '%s\n' "$rc" >"$out/exit-code.txt"
    echo "$rc"
}

check_fallback() {
    local mode=$1 out=$2 rc=$3 alloc=$4 free=$5
    [ "$rc" = 0 ] || { echo "FAIL $mode fallback exited $rc"; return 1; }
    [ "$(find "$out" -name '*.mrc' -type f | wc -l | tr -d ' ')" = 1 ] || {
        echo "FAIL $mode fallback did not publish one corrected image"; return 1;
    }
    [ "$(find "$out" -name corrected_micrographs.star -type f | wc -l | tr -d ' ')" = 1 ] || {
        echo "FAIL $mode fallback did not publish the joint STAR"; return 1;
    }
    [ "$(count_markers 'Materialized native uint16 frames as float for CPU fallback.' "$out")" -ge 1 ] || {
        echo "FAIL $mode did not witness host float materialization"; return 1;
    }
    [ "$(count_markers '[u16fault] stage-alloc-ok' "$out")" = "$alloc" ] || {
        echo "FAIL $mode staging allocation count differs"; return 1;
    }
    [ "$(count_markers '[u16fault] stage-free-ok' "$out")" = "$free" ] || {
        echo "FAIL $mode staging release count differs"; return 1;
    }
    "$COMPARATOR" "$WORK/healthy/out" "$out" --manifest "$MANIFEST" --products-only
}

echo "=== healthy resident path: staging released after forward FFT ==="
[ "$(count_markers '[u16fault] stage-alloc-ok' "$WORK/healthy/out")" = 1 ] || {
    echo "FAIL healthy path did not allocate its one-frame device staging buffer"; exit 1;
}
[ "$(count_markers '[u16fault] stage-free-ok' "$WORK/healthy/out")" = 1 ] || {
    echo "FAIL healthy path did not release its one-frame device staging buffer"; exit 1;
}
[ "$(count_markers 'Released native uint16 host staging after device forward FFT.' "$WORK/healthy/out")" -ge 1 ] || {
    echo "FAIL healthy path did not witness host staging lifetime transition"; exit 1;
}

echo "=== recoverable device-staging allocation failure ==="
rc=$(run_u16 alloc "$WORK/alloc/out")
check_fallback alloc "$WORK/alloc/out" "$rc" 0 0
[ "$(count_markers 'injected stage allocation failure' "$WORK/alloc/out")" = 1 ] || {
    echo "FAIL allocation injection did not hit the U16 staging allocation"; exit 1;
}

echo "=== recoverable U16 H2D failure ==="
rc=$(run_u16 h2d "$WORK/h2d/out")
check_fallback h2d "$WORK/h2d/out" "$rc" 1 1
[ "$(count_markers 'injected stage H2D failure' "$WORK/h2d/out")" = 1 ] || {
    echo "FAIL H2D injection did not hit the U16 staging upload"; exit 1;
}

echo "=== recoverable conversion-kernel launch-status failure ==="
rc=$(run_u16 kernel-recoverable "$WORK/kernel-recoverable/out")
check_fallback kernel-recoverable "$WORK/kernel-recoverable/out" "$rc" 1 1
[ "$(count_markers 'injected post-launch conversion status: cudaErrorInvalidConfiguration' "$WORK/kernel-recoverable/out")" = 1 ] || {
    echo "FAIL conversion launch-status injection did not run"; exit 1;
}

echo "=== fatal conversion-kernel status fails closed without CPU retry ==="
rc=$(run_u16 kernel-fatal "$WORK/kernel-fatal/out")
[ "$rc" != 0 ] || { echo "FAIL fatal U16 error was reported as success"; exit 1; }
[ "$(find "$WORK/kernel-fatal/out" -name '*.mrc' -type f | wc -l | tr -d ' ')" = 0 ] || {
    echo "FAIL fatal U16 error published a corrected image"; exit 1;
}
[ "$(find "$WORK/kernel-fatal/out" -name '*.star' -type f | wc -l | tr -d ' ')" = 0 ] || {
    echo "FAIL fatal U16 error published a per-movie or joint STAR"; exit 1;
}
[ "$(count_markers 'injected post-launch conversion status: cudaErrorIllegalAddress' "$WORK/kernel-fatal/out")" = 1 ] || {
    echo "FAIL fatal conversion launch-status injection did not run"; exit 1;
}
[ "$(count_markers 'Materialized native uint16 frames as float for CPU fallback.' "$WORK/kernel-fatal/out")" = 0 ] || {
    echo "FAIL fatal U16 error incorrectly entered CPU fallback"; exit 1;
}
[ "$(count_markers '[u16fault] stage-free-ok' "$WORK/kernel-fatal/out")" = 1 ] || {
    echo "FAIL fatal U16 path did not release the device staging buffer"; exit 1;
}
grep -R -h -F "Refusing CPU fallback after a fatal device error." "$WORK/kernel-fatal/out" \
    --binary-files=without-match >/dev/null || { echo "FAIL fatal failure-state guard did not fire"; exit 1; }

echo "PASS U16 failure controls. Artifacts retained at $WORK"
echo "NOTE launch-status faults are injected status codes; genuine device poisoning remains untested."
