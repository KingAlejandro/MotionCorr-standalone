#!/bin/bash
# Issue #69: RESULTS.md carries a handful of figures that go stale whenever the source
# or the CPU arm moves -- the run timestamps, the candidate binary hash, and the names
# of accessors that exist in the source. Hand-editing them failed three rounds running,
# with the same two lines blocked, fixed, and blocked again one head later.
#
# This does not regenerate the prose. It FAILS when the prose disagrees with the
# evidence or the source, so the drift is caught here rather than by a reviewer.
#
# Usage: check_volatile_figures.sh [repo_root]
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/../../.." && pwd)}"
R="$ROOT/docs/issue69/RESULTS.md"
PROV="$ROOT/docs/issue69/evidence/cpu-provenance.txt"
REVAL="$ROOT/docs/issue69/evidence/cpu-revalidation.log"
fail=0
note() { echo "  $*"; }

for f in "$R" "$PROV" "$REVAL"; do
    [ -r "$f" ] || { echo "FAIL cannot read $f"; exit 2; }
done

echo "== 1. candidate binary hash quoted in RESULTS must be the one in the evidence =="
cand=$(awk '/=== binaries ===/{f=1;next} f&&/build-cand\/motioncorr/{print substr($1,1,8);exit}' "$PROV")
[ -n "$cand" ] || { echo "FAIL could not read the candidate hash from the evidence"; exit 2; }
note "evidence candidate: ${cand}…"
# Any 8-hex-digit token followed by the ellipsis, presented as a candidate, must match.
stale=$(grep -oE 'candidate `[0-9a-f]{8}' "$R" | sed 's/.*`//' | sort -u | grep -v "^${cand}$" || true)
if [ -n "$stale" ]; then
    echo "FAIL RESULTS quotes candidate hash(es) not in the evidence: $stale"; fail=1
else note "RESULTS agrees"; fi

echo "== 2. run timestamps quoted in RESULTS must be this run's =="
start=$(grep -m1 -oE '^START [0-9T:+-]+' "$REVAL" | awk '{print $2}')
done_=$(grep -m1 -oE '^DONE [0-9T:+-]+' "$REVAL" | awk '{print $2}')
note "evidence run: ${start} .. ${done_}"
for ts in $(grep -oE '2026-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' "$R" | sort -u); do
    if [ "$ts" != "${start%%+*}" ] && [ "$ts" != "${done_%%+*}" ]; then
        # Timestamps naming a *preserved historical* run are legitimate; those live in
        # section 1's failure paragraph and section 5c. Only flag ones claimed as current.
        if grep -n "$ts" "$R" | grep -qi "current head"; then
            echo "FAIL RESULTS calls $ts the current head; evidence says ${start%%+*}"; fail=1
        else note "historical timestamp $ts (not claimed current) - ok"; fi
    fi
done
[ $fail -eq 0 ] && note "no timestamp claimed current that disagrees with the evidence"

echo "== 3. every C++ identifier RESULTS presents in a code span must exist in src/ =="
missing=""
for sym in $(grep -oE '`[a-zA-Z_][a-zA-Z0-9_]*\(\)`|`get[A-Z][a-zA-Z0-9_]*`' "$R" | tr -d '`()' | sort -u); do
    grep -rqE "\b${sym}\b" "$ROOT/src" "$ROOT/tests" || missing="$missing $sym"
done
if [ -n "$missing" ]; then
    echo "FAIL RESULTS names identifiers absent from src/ and tests/:$missing"; fail=1
else note "every named identifier exists"; fi

echo
if [ $fail -ne 0 ]; then echo "FAIL volatile figures in RESULTS.md disagree with the evidence or the source"; exit 1; fi
echo "PASS volatile figures agree with the evidence and the source"
