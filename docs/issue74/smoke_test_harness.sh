#!/bin/bash
# Issue #74: smoke-test the GPU harness without a GPU allocation.
#
# Two attempts at the real job were lost, the second to a `set -u` fatal inside
# a function that had never been executed. An exclusive GPU allocation is too
# scarce to spend on discovering shell bugs, so this exercises the harness's own
# function bodies -- extracted from issue74_gpu.sbatch, not copied, so the test
# cannot drift from the thing it is testing -- against a stub binary that
# produces the outputs the real one produces.
#
# It proves nothing scientific. It only proves the harness runs.
#
# Usage: bash smoke_test_harness.sh [path-to-issue74_gpu.sbatch]

set -uo pipefail

SBATCH_FILE="${1:-$(dirname "$0")/issue74_gpu.sbatch}"
[ -f "$SBATCH_FILE" ] || { echo "no such harness: $SBATCH_FILE"; exit 2; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

# ---- stub environment -------------------------------------------------------
E="$T/ev"; W="$T/w"
mkdir -p "$E" "$W/in" "$W/out" "$W/t" "$W/in/Movies"
SUMMARY="$E/summary.txt"; : > "$SUMMARY"
ORDER=0
MC_ARGS=(--j 8 --use_own --dose_weighting --seed 1)
CAND_BIN="$T/stub-motioncorr"
BASE_BIN="$T/stub-motioncorr"

# A stub that emits exactly the markers and files the harness parses.
cat > "$CAND_BIN" <<'STUB'
#!/bin/bash
out=""; prev=""
for a in "$@"; do [ "$prev" = "--o" ] && out="$a"; prev="$a"; done
mode=on
case "${RELION_CUDA_DETAILED_PROFILE:-1}" in 0|off|OFF|false|FALSE|no) mode=off;; esac
echo "Using CUDA acceleration on GPU device 0 for global alignment."
mkdir -p "$out/Movies"
for i in $(seq -w 1 24); do
  b="$out/Movies/20170629_000${i}_frameImage"
  { for s in $(seq 1 27); do
      echo " [CUDA Profile $s]"
      echo "   Detailed event profiling:     $mode"
    done
    echo " [CUDA Global Alignment] completed; converged=yes"
    echo "Full movie wall time: 1.799 s"
  } > "$b.log"
  echo "deterministic-trajectory-$i" > "$b.star"
  echo "fake" > "$b.mrc"
done
echo "done" > "$out/corrected_micrographs.star"
STUB
chmod +x "$CAND_BIN"

# ---- extract the real function bodies --------------------------------------
FUNCS="$T/funcs.sh"
# The name pattern must allow digits (run_all24) and any spacing before the
# brace (det_sites has two). Getting either wrong silently drops a function,
# and the test then "passes" a function it never loaded.
DEFRE='^[a-z_][a-z0-9_]*\(\)[[:space:]]*\{'
awk '
  # A one-line function (name() { ...; }) closes on its own line; a multi-line
  # one closes at a "}" in column 0. Missing the first case silently swallows
  # every following top-level statement into the extract.
  /^[a-z_][a-z0-9_]*\(\)[[:space:]]*\{/ && /\}[[:space:]]*$/ { print; next }
  /^[a-z_][a-z0-9_]*\(\)[[:space:]]*\{/ { inf=1 }
  inf { print }
  inf && /^\}/ { inf=0 }
' "$SBATCH_FILE" > "$FUNCS"

WANT=$(grep -cE "$DEFRE" "$SBATCH_FILE")
NFUNC=$(grep -cE "$DEFRE" "$FUNCS")
echo "extracted $NFUNC of $WANT function definitions from $(basename "$SBATCH_FILE")"
if [ "$NFUNC" -ne "$WANT" ] || [ "$NFUNC" -lt 9 ]; then
    echo "FAIL: extraction is incomplete (want $WANT, at least 9)"; exit 1
fi
# The extract must be definitions only. Any top-level statement here means the
# extractor lost track and the test would execute harness body code on source.
STRAY=$(grep -vE "$DEFRE" "$FUNCS" | grep -E '^[^ }]' || true)
if [ -n "$STRAY" ]; then
    echo "FAIL: extract contains top-level statements:"; echo "$STRAY" | head; exit 1
fi
# shellcheck disable=SC1090
source "$FUNCS"

fails=0
expect() { # expect <label> <expected> <actual>
    if [ "$2" = "$3" ]; then echo "ok   $1 = $3"
    else echo "FAIL $1: expected [$2] got [$3]"; fails=$((fails+1)); fi
}

echo "--- record/gate"
record PASS "smoke" > /dev/null
gate "a passing gate" true > /dev/null
gate "a failing gate" false > /dev/null
expect "summary PASS count" 2 "$(grep -c '^PASS' "$SUMMARY")"
expect "summary FAIL count" 1 "$(grep -c '^FAIL' "$SUMMARY")"

echo "--- run_all24 (the function that killed job 3510287)"
run_all24 cand-on  "$CAND_BIN" ""  > "$T/r1.log" 2>&1 || true
run_all24 cand-off "$CAND_BIN" "0" > "$T/r2.log" 2>&1 || true
expect "cand-on startup markers"    1  "$(cat "$E/run-cand-on.startup_markers")"
expect "cand-on completion markers" 24 "$(cat "$E/run-cand-on.completion_markers")"
expect "cand-off completion markers" 24 "$(cat "$E/run-cand-off.completion_markers")"

echo "--- det_values / det_sites (the switch-actually-switched check)"
expect "cand-on value"  "on"  "$(det_values "$W/out/cand-on")"
expect "cand-off value" "off" "$(det_values "$W/out/cand-off")"
expect "profile sites per movie log" 27 "$(det_sites "$W/out/cand-on")"

echo "--- timed_run (wall/RSS parsing and the trajectory digest)"
# Section 8 writes this header before its first timed_run; mirror it, or the
# NR>1 aggregations below silently drop a real row.
printf 'order\ttag\twall_s\tmax_rss_kb\tstar_digest\n' > "$E/timing.tsv"
timed_run cand-on  "$CAND_BIN" ""  > "$T/t1.log" 2>&1 || true
timed_run cand-off "$CAND_BIN" "0" > "$T/t2.log" 2>&1 || true
expect "timing rows" 2 "$(awk 'NR>1' "$E/timing.tsv" | wc -l | tr -d ' ')"
WALL=$(awk 'NR==2{print $3}' "$E/timing.tsv")
RSS=$(awk 'NR==2{print $4}' "$E/timing.tsv")
DIG=$(awk 'NR>1{print $5}' "$E/timing.tsv" | sort -u | wc -l | tr -d ' ')
case "$WALL" in *:*) echo "ok   wall parsed = $WALL";; *) echo "FAIL wall not parsed: [$WALL]"; fails=$((fails+1));; esac
case "$RSS" in ''|*[!0-9]*) echo "FAIL rss not parsed: [$RSS]"; fails=$((fails+1));; *) echo "ok   rss parsed = $RSS";; esac
expect "identical trajectories across arms (digest count)" 1 "$DIG"

echo "--- sample_pair (nvidia-smi absent here; must not be fatal)"
if command -v nvidia-smi > /dev/null; then echo "skip: real nvidia-smi present"
else sample_pair on "" > "$T/m.log" 2>&1; echo "ok   sample_pair returned $?"; fi

echo
if [ "$fails" -eq 0 ]; then echo "HARNESS SMOKE TEST: PASS"; exit 0; fi
echo "HARNESS SMOKE TEST: FAIL ($fails)"; exit 1
