#!/bin/bash
# usage: mutants_h5.sh   (on cpu64) Each mutant of the isotropic-weight change must make IsotropicWeight FAIL.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
M=$DS_SC/mut-h5; rm -rf $M; mkdir -p $M/src; cp -a $DS_SC/src-h5/. $M/src/
F=$M/src/src/motioncorr_runner.cpp; cp $F $M/orig.cpp
lane cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF > $M/configure.log 2>&1 || { echo configure failed; exit 3; }
mutate() {
  cp $M/orig.cpp $F; $DS_PY -I - "$F" "$1" <<'PY'
import sys
p, name = sys.argv[1], sys.argv[2]; s = open(p).read()
def must(old, new):
    global s
    assert s.count(old) == 1, (name, old[:50]); s = s.replace(old, new)
XN = "return (is_global && isotropic) ? (RFLOAT)pnx : (RFLOAT)nfx;"
if name == 'flag-ignored':      must(XN, "return (RFLOAT)nfx;")
elif name == 'wrong-norm':      must(XN, "return (is_global && isotropic) ? (RFLOAT)(pnx / 2) : (RFLOAT)nfx;")
elif name == 'leaks-to-patch':  must(XN, "return (isotropic) ? (RFLOAT)pnx : (RFLOAT)nfx;")
elif name == 'formula-factor':  must("return exp(- 2 * dist2 * scaled_B);", "return exp(- dist2 * scaled_B);")
elif name == 'prod-norm-moved': must("RFLOAT dist2 = ly2 + x * (RFLOAT)x / (x_norm * x_norm);", "RFLOAT dist2 = ly2 + x * (RFLOAT)x / (65.0 * 65.0);")
open(p, 'w').write(s)
PY
}
for m in flag-ignored wrong-norm leaks-to-patch formula-factor prod-norm-moved; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target isotropic_weight --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $M/build/isotropic_weight > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: isotropic_weight rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
cp $M/orig.cpp $F; lane cmake --build $M/build --target isotropic_weight --parallel 8 > $M/build-restored.log 2>&1
lane $M/build/isotropic_weight > $M/run-restored.log 2>&1; echo "restored original: rc=$? (must be 0)"
