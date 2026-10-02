#!/usr/bin/env python3
"""Add NVTX ranges to MotionCorr by reusing the existing RCTIC/RCTOC stage
markers. Marker labels are checked for balanced, properly nested textual order
before writing. This is not a proof of every runtime control-flow path.
Enabled only under -DMC_NVTX;
the stock TIMING path and the no-op path are untouched."""
import sys, re, pathlib

p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "src/motioncorr_runner.cpp")
s = p.read_text()
orig = s

# Ignore comments, string/character literals and preprocessor definitions: only
# literal stage call sites participate in the textual push/pop contract.
code = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
              lambda m: '\n' * m.group(0).count('\n'), s)
code = re.sub(r'(?m)^[ \t]*#.*$', '', code)
stack = []
for marker in re.finditer(r'\bRCT(IC|OC)\(\s*(TIMING_[A-Z0-9_]+)\s*\)', code):
    kind, label = marker.groups()
    if kind == 'IC':
        stack.append(label)
    elif not stack or stack.pop() != label:
        raise SystemExit('patch_nvtx: unbalanced/misordered stage marker ' + label +
                         '; refusing without modifying source')
if stack:
    raise SystemExit('patch_nvtx: unclosed stage marker ' + stack[-1] +
                     '; refusing without modifying source')

# 1. Insert the MC_NVTX macro branch before the final #else of the TIMING block.
labels = sorted(set(re.findall(r'\bRCT(?:IC|OC)\((TIMING_[A-Z0-9_]+)\)', s)))
defs = "\n".join('\t#define %s "%s"' % (l, l[len("TIMING_"):].lower().replace("_"," "))
                 for l in labels)
branch = '''#elif defined(MC_NVTX)
\t#include <nvtx3/nvToolsExt.h>
\tstruct McNvtxScope {
\t\texplicit McNvtxScope(const char *n) { nvtxRangePushA(n); }
\t\t~McNvtxScope() { nvtxRangePop(); }
\t};
\t#define RCTIC(label) nvtxRangePushA(label)
\t#define RCTOC(label) nvtxRangePop()
\t#define MC_SCOPE(n) McNvtxScope _mc_nvtx_scope_(n)
%s

#else
\t#define RCTIC(label)
\t#define RCTOC(label)
''' % defs

matched = []
old_else = "#else\n\t#define RCTIC(label)\n\t#define RCTOC(label)\n#endif"
if s.count(old_else) != 1:
    raise SystemExit("patch_nvtx: anchor RCTIC-#else matched %d times, expected 1. "
                     "This source is not supported; refusing rather than emitting a half-patched tree."
                     % s.count(old_else))
s = s.replace(old_else, branch + "#endif")

# MC_SCOPE must exist (as a no-op) on the TIMING and plain paths too.
s = s.replace("#endif\n\nvoid MotioncorrRunner::read(",
              "#endif\n#ifndef MC_SCOPE\n#define MC_SCOPE(n)\n#endif\n\nvoid MotioncorrRunner::read(", 1)

# 2. Per-movie range. RAII, so the early `return false` stays balanced.
# The signature changed after 1d7e13f (effective_expected_frames was added), so try
# each known variant and record which one matched. Both the search text and the
# replacement text have to carry the same signature or the patched tree declares a
# function that matches no declaration.
MOVIE_SIGS = [
    "bool MotioncorrRunner::executeOwnMotionCorrection(Micrograph &mic, int effective_expected_frames) {",
    "bool MotioncorrRunner::executeOwnMotionCorrection(Micrograph &mic) {",
]
sig = next((g for g in MOVIE_SIGS if s.count(g + "\n\ttimeval movie_start_time;") == 1), None)
if sig is None:
    raise SystemExit("patch_nvtx: no known executeOwnMotionCorrection signature found. Tried:\n  "
                     + "\n  ".join(MOVIE_SIGS)
                     + "\nThis source is not supported; refusing rather than emitting a half-patched tree.")
anchor = sig + "\n\ttimeval movie_start_time;"
s = s.replace(anchor,
              sig + "\n"
              "\tMC_SCOPE(\"MOVIE (executeOwnMotionCorrection)\");\n"
              "\ttimeval movie_start_time;", 1)
matched.append("movie-scope: " + sig.split("(")[1].rstrip(" {"))

# 3. Output handoff -- the one real stage with no RCTIC marker.
# Before the async writer landed this was a direct blocking Iref.write, so the scope
# measured the write. Current main queues to a writer thread, so the same position
# measures only the handoff and the scope is named accordingly. The writer drain is
# inside the process wall but inside no NVTX stage; do not read it off this scope.
OUT_SITES = [
    ("submit output", "\t\tsubmitImageWrite(Iref, fn_avg, write_float16 ? Float16: Float);"),
    ("write output",  "\t\tIref.write(fn_avg, -1, false, WRITE_OVERWRITE, write_float16 ? Float16: Float);"),
]
site = next(((nm, w) for nm, w in OUT_SITES if s.count(w) == 1), None)
if site is None:
    raise SystemExit("patch_nvtx: no known output-write site found. Tried:\n  "
                     + "\n  ".join(w.strip() for _, w in OUT_SITES)
                     + "\nThis source is not supported; refusing rather than emitting a half-patched tree.")
oname, wr = site
s = s.replace(wr, "\t\t{ MC_SCOPE(\"" + oname + "\");\n" + wr + "\n\t\t}", 1)
matched.append("output-scope: " + oname)

if s == orig:
    raise SystemExit("patch_nvtx: no change applied")
p.write_text(s)
print("patched: %d stage labels; %s" % (len(labels), "; ".join(matched)))
for l in labels: print("   ", l)
