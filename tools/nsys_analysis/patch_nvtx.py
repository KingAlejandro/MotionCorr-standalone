#!/usr/bin/env python3
"""Add NVTX ranges to MotionCorr by reusing the existing RCTIC/RCTOC stage
markers. 35 RCTIC/RCTOC pairs, verified balanced and non-interleaved, so
nvtxRangePush/Pop maps onto them one-for-one. Enabled only under -DMC_NVTX;
the stock TIMING path and the no-op path are untouched."""
import sys, re, sys, pathlib

p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "src/motioncorr_runner.cpp")
s = p.read_text()
orig = s

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

old_else = "#else\n\t#define RCTIC(label)\n\t#define RCTOC(label)\n#endif"
assert s.count(old_else) == 1, "RCTIC #else block not found exactly once"
s = s.replace(old_else, branch + "#endif")

# MC_SCOPE must exist (as a no-op) on the TIMING and plain paths too.
s = s.replace("#endif\n\nvoid MotioncorrRunner::read(",
              "#endif\n#ifndef MC_SCOPE\n#define MC_SCOPE(n)\n#endif\n\nvoid MotioncorrRunner::read(", 1)

# 2. Per-movie range. RAII, so the early `return false` stays balanced.
anchor = ("bool MotioncorrRunner::executeOwnMotionCorrection(Micrograph &mic) {\n"
          "\ttimeval movie_start_time;")
assert s.count(anchor) == 1, "executeOwnMotionCorrection anchor not found"
s = s.replace(anchor,
              "bool MotioncorrRunner::executeOwnMotionCorrection(Micrograph &mic) {\n"
              "\tMC_SCOPE(\"MOVIE (executeOwnMotionCorrection)\");\n"
              "\ttimeval movie_start_time;", 1)

# 3. Final output write -- the one real stage with no RCTIC marker.
wr = "\t\tIref.write(fn_avg, -1, false, WRITE_OVERWRITE, write_float16 ? Float16: Float);"
assert s.count(wr) == 1, "final Iref.write not found exactly once"
s = s.replace(wr, "\t\t{ MC_SCOPE(\"write output\");\n" + wr + "\n\t\t}", 1)

assert s != orig
p.write_text(s)
print("patched: %d stage labels, +movie scope, +write scope" % len(labels))
for l in labels: print("   ", l)
