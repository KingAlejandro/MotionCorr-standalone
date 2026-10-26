#!/bin/bash
# usage: mutants_h2.sh   (on cpu64) Each mutant of the H2 change must make CoupledPeak FAIL.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
M=$DS_SC/mut-h2; rm -rf $M; mkdir -p $M/src; cp -a $DS_SC/src-h2/. $M/src/
F=$M/src/src/motioncorr_runner.cpp; cp $F $M/orig.cpp
lane cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF > $M/configure.log 2>&1 || { echo configure failed; exit 3; }
mutate() {
  cp $M/orig.cpp $F; $DS_PY -I - "$F" "$1" <<'PY'
import sys
p, name = sys.argv[1], sys.argv[2]; s = open(p).read()
def must(old, new):
    global s
    assert s.count(old) == 1, (name, old[:50]); s = s.replace(old, new)
if name == 'drop-hxy':          must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = 0.0 * (")
elif name == 'sign-hxy':        must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = -0.25 * (")
elif name == 'half-stencil':    must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = 0.5 * (")
elif name == 'no-negdef-guard': must("if (!(hxx < 0 && det > 0)) return 1;", "if (det == 0) return 1;")
elif name == 'no-offset-guard': must("if (!(std::abs(ox) <= 1.0 && std::abs(oy) <= 1.0)) return 2;", "")
elif name == 'swap-axes':       must("dx = ox; dy = oy;", "dx = oy; dy = ox;")
elif name == 'global-leaks':    must("experimental_coupled_peak == 2 || (experimental_coupled_peak == 1 && is_global)", "experimental_coupled_peak >= 1")
elif name == 'not-applied':     must("if (verdict == 0) {\n\t\t\t\t\tcur_xshifts[iframe] = posx + dx;", "if (false) {\n\t\t\t\t\tcur_xshifts[iframe] = posx + dx;")
open(p, 'w').write(s)
PY
}
for m in drop-hxy sign-hxy half-stencil no-negdef-guard no-offset-guard swap-axes global-leaks not-applied; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target coupled_peak --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $M/build/coupled_peak > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: coupled_peak rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
cp $M/orig.cpp $F; lane cmake --build $M/build --target coupled_peak --parallel 8 > $M/build-restored.log 2>&1
lane $M/build/coupled_peak > $M/run-restored.log 2>&1; echo "restored original: rc=$? (must be 0)"
