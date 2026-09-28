#!/bin/bash
# Relocation-level check: did --wrap actually redirect production call sites, or is
# the harness silently no-opping? Read-only disassembly; needs no device.
set -u
B=~/MotionCorr-i69/build
export PATH=/usr/local/cuda/bin:$PATH
objdump -d --demangle "$B/cuda_fault_matrix" > /tmp/fm.dis

# Walk the disassembly, tracking which function each call belongs to.
python3 - <<'PY'
import re, collections
cur = None
per_fn = collections.defaultdict(collections.Counter)
INTERESTING = re.compile(r'(cudaMalloc|cudaFree|cudaMemcpy|cudaMemset|cudaDeviceSynchronize|cudaEventCreate|cudaEventDestroy|cufftCreate|cufftMakePlanMany|cufftSetWorkArea|cufftPlanMany|cufftDestroy|cufftExecR2C|cufftExecC2R)')
for line in open('/tmp/fm.dis'):
    m = re.match(r'^[0-9a-f]+ <(.+)>:$', line.strip())
    if m:
        cur = m.group(1); continue
    if cur and 'call' in line:
        t = re.search(r'<([^>]+)>\s*$', line.strip())
        if t and INTERESTING.search(t.group(1)):
            per_fn[cur][t.group(1)] += 1

def show(pred, title):
    print(title)
    any_row = False
    for fn, counter in sorted(per_fn.items()):
        if not pred(fn): continue
        any_row = True
        for sym, n in sorted(counter.items()):
            print("  %-58s %2d x %s" % (fn[:58], n, sym))
    if not any_row: print("  (none)")
    print()

prod = lambda fn: not fn.startswith('__wrap_') and 'main' not in fn and 'anonymous namespace' not in fn
show(lambda fn: fn.startswith('cudaAlignPatchDevice'),      "cudaAlignPatchDevice  (the F1 site):")
show(lambda fn: fn.startswith('cudaAlignPatch('),           "cudaAlignPatch  (the F2 wrapper):")
show(lambda fn: fn.startswith('CudaMovieSession::preparePatchInVram'), "CudaMovieSession::preparePatchInVram  (the F3 site):")

# The load-bearing assertion: no function from motioncorr_core may still reach a bare
# interposed symbol. A bare call is legitimate from exactly two places, both in the
# test's own translation unit:
#   * a __wrap_ thunk, where it is the __real_* forward, and
#   * runTrial/main, whose post-trial reclaim deliberately uses __real_* so that
#     cleaning up after a leaking trial does not perturb the next trial's accounting.
TEST_OWN = ('__wrap_', 'main', '(anonymous namespace)::runTrial')

def is_test_own(fn):
    return any(fn.startswith(p) for p in TEST_OWN)

leaks = []
for fn, counter in per_fn.items():
    if is_test_own(fn): continue
    for sym in counter:
        if not sym.startswith('__wrap_') and '@plt' in sym:
            leaks.append((fn, sym, counter[sym]))
print("Production (motioncorr_core) call sites still reaching a bare interposed")
print("symbol -- must be 0, otherwise the harness silently observes nothing: %d" % len(leaks))
for fn, sym, n in leaks: print("  BYPASS %-50s %d x %s" % (fn[:50], n, sym))
print()
print("Bare calls from the test's own code (expected, by construction):")
for fn, counter in sorted(per_fn.items()):
    if not is_test_own(fn): continue
    for sym, n in sorted(counter.items()):
        if '@plt' in sym:
            role = "__real_ forward" if fn.startswith('__wrap_') else "post-trial reclaim"
            print("  %-46s %d x %-26s (%s)" % (fn[:46], n, sym, role))
PY
