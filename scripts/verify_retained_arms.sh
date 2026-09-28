#!/bin/bash
# Re-verify retained #94 arm outputs with the maintained comparison, read-only.
#
# This exists because the whole-file parity claim rests on a `--pair` run over
# the retained SCARF trees, and that run previously had no committed
# provenance: the sbatch script did not perform it, so a reader could not tell
# what command produced the verification artifact. Now they can.
#
# Read-only: opens retained outputs, writes only its two report files. No GPU,
# no allocation, no build, no timing.
set -u

ROOT="${1:-}"
OUT="${2:-$PWD}"
TOOL="$(cd "$(dirname "$0")/.." && pwd)/tools/compare_prefetch_arms.py"

[ -n "$ROOT" ] || { echo "usage: $0 <runs-root> [report-dir]" >&2; exit 2; }
[ -f "$TOOL" ] || { echo "cannot find $TOOL" >&2; exit 2; }

# Fatal first: a comparison whose own negative control fails certifies nothing.
python3 "$TOOL" --self-test > "$OUT/full_header_verification_negative_control.txt" 2>&1
rc=$?
echo "negative control rc=$rc"
[ $rc -eq 0 ] || { echo "SELF-TEST FAILED -- refusing to verify with it" >&2; exit 3; }

{
	echo "tool:      $TOOL"
	echo "tool_sha:  $(sha256sum "$TOOL" | awk '{print $1}')"
	echo "root:      $ROOT"
	echo "host:      $(hostname)"
	echo "date_utc:  $(date -u +%FT%TZ)"
	echo "command:   $0 $ROOT $OUT"
	echo
	pairs=0; clean=0
	for d in "$ROOT"/*/; do
		[ -d "$d/correctness_off" ] || continue
		echo "=== $(basename "$d") ==="
		echo "-- correctness_off vs correctness_on"
		python3 "$TOOL" --pair "$d/correctness_off" "$d/correctness_on" 2>&1 | grep -vE "^[AB]: "
		pairs=$((pairs+1))
		for p in 1 2 3; do
			off=$(ls -d "$d"/pair${p}_*_off 2>/dev/null | head -1)
			on=$(ls -d "$d"/pair${p}_*_on 2>/dev/null | head -1)
			[ -n "$off" ] && [ -n "$on" ] || continue
			echo "-- pair$p: $(basename "$off") vs $(basename "$on")"
			python3 "$TOOL" --pair "$off" "$on" 2>&1 | grep -vE "^[AB]: "
			pairs=$((pairs+1))
		done
	done
	echo
	echo "pairs_compared: $pairs"
	echo "DONE_VERIFY"
} > "$OUT/full_header_verification.txt" 2>&1

clean=$(grep -c "^PROBLEMS: none" "$OUT/full_header_verification.txt")
total=$(grep -c "^-- " "$OUT/full_header_verification.txt")
echo "pairs clean: $clean / $total"
[ "$clean" -eq "$total" ] && [ "$total" -gt 0 ]
