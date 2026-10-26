#!/bin/bash
# usage: mutants_h3.sh   (on cpu64) Each mutant of the ported DC hook call site must make CcfDcHook FAIL
# (the three CPU mutants of the #262 oracle: restore the bin, zero the wrong bin, swap the stage).
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
M=$DS_SC/mut-h3; rm -rf $M; mkdir -p $M/src; cp -a $DS_SC/src-h3/. $M/src/
F=$M/src/src/motioncorr_runner.cpp; cp $F $M/orig.cpp
lane cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF -DMC_EXPERIMENT_CCF_DC=ON > $M/configure.log 2>&1 || { echo configure failed; exit 3; }
mutate() {
  cp $M/orig.cpp $F; $DS_PY -I - "$F" "$1" <<'PY'
import sys
p, name = sys.argv[1], sys.argv[2]; s = open(p).read()
Z = "DIRECT_A2D_ELEM(Fccs[tid], 0, 0) = fComplex(0.f, 0.f);"
def must(old, new):
    global s
    assert s.count(old) == 1, (name, old[:50]); s = s.replace(old, new)
if name == 'cpu_restore':      must(Z, "(void)0;")
elif name == 'cpu_wrong_bin':  must(Z, "DIRECT_A2D_ELEM(Fccs[tid], 0, 1) = fComplex(0.f, 0.f);")
elif name == 'cpu_stage_swap': must("experimentCcfDcZero(is_global, EXP_DC_CPU, 1)", "experimentCcfDcZero(!is_global, EXP_DC_CPU, 1)")
open(p, 'w').write(s)
PY
}
for m in cpu_restore cpu_wrong_bin cpu_stage_swap; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target ccf_dc_hook --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $M/build/ccf_dc_hook > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: ccf_dc_hook rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
cp $M/orig.cpp $F; lane cmake --build $M/build --target ccf_dc_hook --parallel 8 > $M/build-restored.log 2>&1
lane $M/build/ccf_dc_hook > $M/run-restored.log 2>&1; echo "restored original: rc=$? (must be 0)"
