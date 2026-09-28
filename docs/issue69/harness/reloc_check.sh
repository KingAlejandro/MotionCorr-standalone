#!/bin/bash
# Issue #69: does --wrap actually redirect motioncorr_core's CUDA call sites into the
# fault matrix's interposers, or is the harness silently observing nothing?
#
# `nm` showing __wrap_* defined proves only that the test translation unit defines
# them; it looks identical whether or not the interposition took effect. This reads the
# linked binary instead.
#
# SCOPE OF THE "0 bypasses" RESULT, stated because it is narrower than it sounds:
#   * it counts direct `call <sym@plt>` sites only. A tail call emitted as
#     `jmp <sym@plt>` or a register-indirect call is not matched;
#   * it depends on CUDA being linked shared (CMakeLists uses CUDA::cudart / CUDA::cufft,
#     not the *_static variants). A statically linked interposed symbol has no PLT entry
#     and would not be flagged;
#   * production code inlined into the test's own functions is exempted along with them.
#     The three call sites that matter are not inlined and are listed explicitly, so the
#     positive evidence for them is direct rather than inferred from the zero.
#
# Read-only. Needs no device. Usage: reloc_check.sh [path-to-cuda_fault_matrix]
set -euo pipefail

BIN="${1:-$HOME/MotionCorr-i69/build/cuda_fault_matrix}"
export PATH="${CUDA_BIN_DIR:-/usr/local/cuda/bin}:$PATH"

[ -r "$BIN" ] || { echo "FAIL: cannot read $BIN"; exit 2; }
DIS="$(mktemp)"; trap 'rm -f "$DIS"' EXIT
objdump -d --demangle "$BIN" > "$DIS"
# A truncated or empty disassembly would otherwise produce a confident "0".
lines=$(wc -l < "$DIS")
[ "$lines" -gt 1000 ] || { echo "FAIL: disassembly is only $lines lines; refusing to report"; exit 2; }
echo "disassembled $BIN -> $lines lines"

DIS="$DIS" python3 - <<'PY'
import collections, os, re, sys

cur, per_fn = None, collections.defaultdict(collections.Counter)
INTERESTING = re.compile(r'(cudaMalloc|cudaFree|cudaMemcpy|cudaMemset|cudaDeviceSynchronize'
                         r'|cudaEventCreate|cudaEventDestroy|cufftCreate|cufftMakePlanMany'
                         r'|cufftSetWorkArea|cufftPlanMany|cufftDestroy|cufftExecR2C|cufftExecC2R)')
for line in open(os.environ['DIS']):
    m = re.match(r'^[0-9a-f]+ <(.+)>:$', line.strip())
    if m:
        cur = m.group(1); continue
    # Match jmp as well as call, so a tail-called bypass is not invisible.
    if cur and re.search(r'\b(call|jmp)\b', line):
        t = re.search(r'<([^>]+)>\s*$', line.strip())
        if t and INTERESTING.search(t.group(1)):
            per_fn[cur][t.group(1)] += 1

# Print full symbol names. Truncating them merged cudaAlignPatchDevice with its .cold
# unwind clone into apparently duplicate rows in an earlier version of this evidence.
def show(prefix, title):
    print(title)
    rows = [(fn, c) for fn, c in sorted(per_fn.items()) if fn.startswith(prefix)]
    if not rows:
        print("  (no matching function found -- check the symbol name)"); print(); return
    for fn, counter in rows:
        print("  in %s" % fn)
        for sym, n in sorted(counter.items()):
            print("      %2d x %s" % (n, sym))
    print()

show('cudaAlignPatchDevice',                    'cudaAlignPatchDevice  (the F1 site):')
show('cudaAlignPatch(',                         'cudaAlignPatch  (the F2 wrapper):')
show('CudaMovieSession::preparePatchInVram',    'CudaMovieSession::preparePatchInVram  (the F3 site):')

# A bare call is legitimate from exactly two places, both in the test's own TU:
# a __wrap_ thunk (the __real_* forward), and runTrial/main's post-trial reclaim,
# which deliberately uses __real_* so cleaning up after a leaking trial does not
# perturb the next trial's accounting.
TEST_OWN = ('__wrap_', 'main', '(anonymous namespace)::runTrial')
is_test_own = lambda fn: any(fn.startswith(p) for p in TEST_OWN)

bypasses = [(fn, sym, n) for fn, c in per_fn.items() if not is_test_own(fn)
            for sym, n in c.items() if not sym.startswith('__wrap_') and '@plt' in sym]
wrapped = sum(n for fn, c in per_fn.items() if not is_test_own(fn)
              for sym, n in c.items() if sym.startswith('__wrap_'))

print("motioncorr_core call sites routed through __wrap_*: %d" % wrapped)
print("motioncorr_core call sites still reaching a bare interposed symbol")
print("  (direct call/jmp to a @plt entry) -- must be 0: %d" % len(bypasses))
for fn, sym, n in bypasses: print("  BYPASS %s  %d x %s" % (fn, n, sym))
print()

# Negative control. The zero above is only meaningful if the filter can produce a
# non-zero, so re-run it with the exemption removed: every __real_* forward inside the
# wrappers must then be reported. If that also comes back 0, the parse is broken and
# the result above means nothing.
control = [(fn, sym, n) for fn, c in per_fn.items() if fn.startswith('__wrap_')
           for sym, n in c.items() if '@plt' in sym]
print("negative control -- same filter with the test-own exemption removed, must be >0: %d"
      % len(control))
for fn, sym, n in sorted(control): print("  %-34s %d x %s  (__real_ forward)" % (fn, n, sym))

if wrapped == 0:
    print("\nFAIL no production call site routes through a wrapper"); sys.exit(1)
if bypasses:
    print("\nFAIL production code bypasses the interposition"); sys.exit(1)
if not control:
    print("\nFAIL the negative control found nothing, so the zero above is not trustworthy")
    sys.exit(1)
print("\nPASS interposition reaches every matched production call site, and the check "
      "demonstrably can fail")
PY
