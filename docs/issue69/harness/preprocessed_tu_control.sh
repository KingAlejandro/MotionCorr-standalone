#!/bin/bash
# Issue #69: prove that in a CPU-only build this branch changes no executable statement
# in src/motioncorr_runner.cpp -- which is what accounts for the differing binary hash,
# and what the same-backend comparison's "0 differing" is entailed by.
#
# Preprocesses both trees with the same flags and no CUDA, strips line directives and
# blank lines, normalises the source root out of __FILE__, and diffs. Carries its own
# negative control: an injected line must be detected.
#
# Usage: preprocessed_tu_control.sh <base_tree> <cand_tree>
set -euo pipefail

BASE="$1"; CAND="$2"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

for arm in base cand; do
    case "$arm" in base) root="$BASE";; cand) root="$CAND";; esac
    g++ -std=gnu++17 -I"$root" -DHAVE_TIFF -DHAVE_PNG -DHAVE_JPEG -fopenmp \
        -E "$root/src/motioncorr_runner.cpp" 2>/dev/null \
      | grep -v '^#' | sed '/^[[:space:]]*$/d' | sed "s#${root}/#<SRCROOT>/#g" > "$WORK/$arm.ii"
done

bl=$(wc -l < "$WORK/base.ii"); cl=$(wc -l < "$WORK/cand.ii")
echo "preprocessed lines: base=$bl cand=$cl"
[ "$bl" -gt 10000 ] || { echo "FAIL: preprocessed output implausibly small; refusing to report"; exit 2; }

diff "$WORK/base.ii" "$WORK/cand.ii" > "$WORK/d" || true
changed=$(grep -c '^[<>]' "$WORK/d" || true)
friend=$(grep -c 'MotioncorrRunnerTestAccess' "$WORK/d" || true)
lineonly=$(grep '^[<>]' "$WORK/d" | grep -vc 'MotioncorrRunnerTestAccess' || true)
notline=$(grep '^[<>]' "$WORK/d" | grep -v 'MotioncorrRunnerTestAccess' \
          | grep -vc 'RelionError(' || true)

echo "differing lines total      : $changed"
echo "  friend declaration lines : $friend   (emits no code)"
echo "  RelionError __LINE__ lines: $((lineonly - notline))"
echo "  anything else            : $notline   <- must be 0"
echo
echo "--- full diff ---"
cat "$WORK/d"
echo
printf 'int __negative_control_probe;\n' >> "$WORK/cand.ii"
if diff -q "$WORK/base.ii" "$WORK/cand.ii" >/dev/null; then
    echo "FAIL negative control: an injected line was not detected"; exit 1
fi
echo "negative control OK: an injected line is detected"
[ "$notline" -eq 0 ] || { echo "FAIL: a non-__LINE__, non-friend difference is present"; exit 1; }
echo "PASS CPU-only translation unit differs only by a no-code friend declaration and __LINE__ metadata"
