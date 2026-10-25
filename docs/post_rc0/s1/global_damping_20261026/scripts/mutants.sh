#!/bin/bash
# usage: mutants.sh   (on cpu64) Each mutant of the global half-gain change must make GlobalHalfGain FAIL.
# One fresh stage of the candidate source (git archive copy), patched in place one mutant at a time.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
M=$DS_SC/mut; rm -rf $M; mkdir -p $M/src; cp -a $DS_SC/src-cand/. $M/src/
F=$M/src/src/motioncorr_runner.cpp; cp $F $M/orig.cpp
lane cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF > $M/configure.log 2>&1 || { echo configure failed; exit 3; }
mutate() { # name python-expr (old->new pairs in env)
  cp $M/orig.cpp $F; $DS_PY -I - "$F" "$1" <<'PY'
import sys
p, name = sys.argv[1], sys.argv[2]; s = open(p).read()
SCALE = """		if (half_gain) {
			for (int iframe = 0; iframe < n_frames; iframe++) {
				cur_xshifts[iframe] *= 0.5;
				cur_yshifts[iframe] *= 0.5;
			}
		}
"""
ACC = """		for (int iframe = 0; iframe < n_frames; iframe++) {
			xshifts[iframe] += cur_xshifts[iframe];
			yshifts[iframe] += cur_yshifts[iframe];"""
def must(old, new):
    global s
    assert s.count(old) == 1, (name, old[:40]); s = s.replace(old, new)
if name == 'accumulate-only':      # re-shift keeps the full update
    must(SCALE, ""); must(ACC, ACC.replace("+= cur_xshifts[iframe];", "+= (half_gain ? 0.5 : 1.0) * cur_xshifts[iframe];").replace("+= cur_yshifts[iframe];", "+= (half_gain ? 0.5 : 1.0) * cur_yshifts[iframe];"))
elif name == 'reshift-only':       # accumulation keeps the full update
    must(SCALE, ""); must("shiftNonSquareImageInFourierTransform(Fframes[iframe], -cur_xshifts[iframe] / pnx, -cur_yshifts[iframe] / pny);", "shiftNonSquareImageInFourierTransform(Fframes[iframe], -(half_gain ? 0.5 : 1.0) * cur_xshifts[iframe] / pnx, -(half_gain ? 0.5 : 1.0) * cur_yshifts[iframe] / pny);")
elif name == 'scaled-sumsq':       # stopping test sees the damped update
    must("		RFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);", "		const RFLOAT g = half_gain ? 0.25 : 1.0;\n		RFLOAT rmsd = std::sqrt(g * (x_sumsq + y_sumsq) / n_frames);")
elif name == 'damp-local':         # flag leaks to local patches
    must("const bool half_gain = is_global && experimental_global_half_gain;", "const bool half_gain = experimental_global_half_gain;")
elif name == 'tolerance-local':    # override leaks to local patches
    must("(is_global && experimental_align_tolerance > 0)", "(experimental_align_tolerance > 0)")
elif name == 'gain-0.6':           # wrong factor
    must("cur_xshifts[iframe] *= 0.5;", "cur_xshifts[iframe] *= 0.6;")
open(p, 'w').write(s)
PY
}
for m in accumulate-only reshift-only scaled-sumsq damp-local tolerance-local gain-0.6; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target global_half_gain --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $M/build/global_half_gain > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: global_half_gain rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
cp $M/orig.cpp $F; lane cmake --build $M/build --target global_half_gain --parallel 8 > $M/build-restored.log 2>&1
lane $M/build/global_half_gain > $M/run-restored.log 2>&1; echo "restored original: rc=$? (must be 0)"
