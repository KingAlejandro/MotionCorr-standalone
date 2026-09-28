#!/bin/bash
# Issue #69: the documents carry figures that go stale whenever the source or a run
# moves. Hand-editing them failed four rounds running; the same two lines were blocked,
# fixed, and blocked again. This check fails when the prose disagrees with the evidence
# or the source.
#
# v2, after a review demonstrated a blind spot in v1: check 2 required the phrase
# "current head" and the timestamp to be on the SAME line, so a line wrap between them
# made it pass on the very defect it was written for. Matching is now paragraph-scoped.
# Check 3's identifier regex only matched `foo()` with literal empty parens, so it would
# have missed `cudaRetryVerdictFor(a, b, c)` -- one of the three defects it was built
# for. It now matches any `ident(`. Coverage extended to control counts and to the other
# documents.
#
# Usage: check_volatile_figures.sh [repo_root]
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/../../.." && pwd)}"
DOCS="$ROOT/docs/issue69/RESULTS.md $ROOT/WORKER_STATUS.md $ROOT/docs/issue69/HANDOFF.md
      $ROOT/agents/designs/issue_69_cuda_failure_contracts.md"
R="$ROOT/docs/issue69/RESULTS.md"
EV="$ROOT/docs/issue69/evidence"
fail=0
note() { echo "  $*"; }
bad()  { echo "  FAIL $*"; fail=1; }

for f in $DOCS "$EV/cpu-provenance.txt" "$EV/cpu-revalidation.log"; do
    [ -r "$f" ] || { echo "FAIL cannot read $f"; exit 2; }
done

echo "== 1. evidence hashes quoted in the docs must exist in the evidence =="
# Only the `xxxxxxxx…` form is checked. That ellipsis convention is used exclusively for
# hashes copied out of the evidence; bare `xxxxxxxx` is a git SHA, which legitimately
# has no business being in an evidence log.
python3 - "$EV" $DOCS <<'PYEOF' || fail=1
import os, re, subprocess, sys
ev, docs = sys.argv[1], sys.argv[2:]
blob = ""
for root, _, files in os.walk(ev):
    for f in files:
        try: blob += open(os.path.join(root, f), errors="ignore").read()
        except OSError: pass
bad = []
for d in docs:
    for h in set(re.findall(r'`([0-9a-f]{8})\u2026`', open(d).read())):
        if h not in blob:
            bad.append((os.path.basename(d), h))
for d, h in sorted(bad):
    print("  FAIL %s quotes evidence hash %s... which appears nowhere in evidence/" % (d, h))
print("  checked %d docs against the evidence tree" % len(docs))
sys.exit(1 if bad else 0)
PYEOF

echo "== 2. no timestamp may be presented as the current run unless it is =="
start=$(grep -m1 -oE '^START [0-9T:+-]+' "$EV/cpu-revalidation.log" | awk '{print $2}')
note "evidence run starts ${start}"
# Paragraph-scoped: a blank line separates paragraphs, so a wrap cannot hide the claim.
if python3 - "$R" "${start%%+*}" <<'PY'
import re, sys
text = open(sys.argv[1]).read(); cur = sys.argv[2]; bad = []
for para in text.split("\n\n"):
    if re.search(r'current head', para, re.I):
        for ts in re.findall(r'2026-\d\d-\d\dT\d\d:\d\d:\d\d', para):
            if ts != cur:
                bad.append(ts)
if bad:
    print("  FAIL these timestamps sit in a paragraph claiming the current head: %s" % sorted(set(bad)))
    sys.exit(1)
sys.exit(0)
PY
then note "no timestamp is wrongly presented as current"; else fail=1; fi

echo "== 3. every C++ identifier the docs present must exist in src/ or tests/ =="
# Exempt: external APIs the documents name deliberately, several of them precisely
# because this issue promises NOT to call them. Absence from src/ is the point.
EXEMPT="cudaDeviceReset cudaGetLastError cudaMalloc cudaFree cudaMemcpy cudaMemset
        cudaEventCreate cudaEventDestroy cudaDeviceSynchronize cudaSetDevice
        cufftCreate cufftDestroy cufftPlanMany cufftMakePlanMany cufftSetWorkArea
        cufftExecR2C cufftExecC2R if for while switch return sizeof"
for sym in $(grep -ohE '`[a-zA-Z_][a-zA-Z0-9_]*\(' $DOCS | tr -d '`(' | sort -u); do
    case " $EXEMPT " in *" $sym "*) continue;; esac
    grep -rqE "\b${sym}\b" "$ROOT/src" "$ROOT/tests" || bad "identifier ${sym}() is named in the docs but absent from src/ and tests/"
done
note "identifier scan complete (external CUDA APIs exempted by name)"

echo "== 4. control counts quoted in RESULTS must match the evidence =="
check_count () {  # $1=regex in docs, $2=regex in evidence, $3=label
    d=$(grep -ohE "$1" $DOCS | grep -oE '[0-9]+' | head -1 || true)
    e=$(grep -rhoE "$2" "$EV" 2>/dev/null | grep -oE '[0-9]+' | sort -u | tail -1 || true)
    if [ -z "$d" ]; then note "$3: not quoted in docs"; return; fi
    if [ -z "$e" ]; then bad "$3: quoted as $d in docs but not found in evidence"; return; fi
    if [ "$d" = "$e" ]; then note "$3: $d matches evidence"; else bad "$3: docs say $d, evidence says $e"; fi
}
check_count '[0-9]+ trials, 0 failures'            '[0-9]+ trials, 0 failures'            "fault-matrix trials"
check_count '[0-9]+ session-state sequences'       '[0-9]+ session-state sequences'       "session-state sequences"
check_count '341735520 pixels'                     '341735520 pixels'                     "all-24 pixel total"

echo
if [ $fail -ne 0 ]; then echo "FAIL volatile figures disagree with the evidence or the source"; exit 1; fi
echo "PASS volatile figures agree with the evidence and the source"
