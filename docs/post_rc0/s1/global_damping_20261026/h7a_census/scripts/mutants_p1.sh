#!/bin/bash
# usage: mutants_p1.sh   (on cpu64) Mutants of the H2 coupled peak and of the DC-hook GPU refusal against the strengthened tests.
#  - the reviewer's five integration mutants (PR286-code-review/local-mutants/mut.py, applied verbatim): transposed gather, y-flipped gather,
#    x-flipped gather, sign of the applied offset, sign of the y offset only -> CoupledPeak must FAIL
#  - the eight earlier H2 mutants -> CoupledPeak must FAIL
#  - refusal of --gpu by the DC hook removed -> CcfDcHookGpuRefusal must FAIL
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
M=$DS_SC/mut-p1; rm -rf $M; mkdir -p $M/src; cp -a $DS_SC/src-p1/. $M/src/
F=$M/src/src/motioncorr_runner.cpp; cp $F $M/orig.cpp
lane cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$DS_PY -DCUDA=OFF -DMC_EXPERIMENT_CCF_DC=ON > $M/configure.log 2>&1 || { echo configure failed; exit 3; }
export MC_EXPERIMENT_CCF_DC_ARM=none
mutate() {
  cp $M/orig.cpp $F; $DS_PY -I - "$F" "$1" <<'PY'
import sys
p, name = sys.argv[1], sys.argv[2]; s = open(p).read()
def must(old, new):
    global s
    assert s.count(old) == 1, (name, old[:60]); s = s.replace(old, new)
G = "v[a][b] = DIRECT_A2D_ELEM(Iccs[tid](), iy3[a], ix3[b]);"
# reviewer's mut.py, verbatim
if name == 'gather-transpose':      must(G, "v[a][b] = DIRECT_A2D_ELEM(Iccs[tid](), iy3[b], ix3[a]);")
elif name == 'gather-yflip':        must("const int iy3[3] = {ipy_n, ipy, ipy_p}", "const int iy3[3] = {ipy_p, ipy, ipy_n}")
elif name == 'gather-xflip':        must("ix3[3] = {ipx_n, ipx, ipx_p}", "ix3[3] = {ipx_p, ipx, ipx_n}")
elif name == 'apply-sign':          must("cur_xshifts[iframe] = posx + dx;\n\t\t\t\t\tcur_yshifts[iframe] = posy + dy;", "cur_xshifts[iframe] = posx - dx;\n\t\t\t\t\tcur_yshifts[iframe] = posy - dy;")
elif name == 'apply-y-only-sign':   must("cur_yshifts[iframe] = posy + dy;", "cur_yshifts[iframe] = posy - dy;")
# the eight earlier H2 mutants
elif name == 'drop-hxy':            must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = 0.0 * (")
elif name == 'sign-hxy':            must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = -0.25 * (")
elif name == 'half-stencil':        must("const RFLOAT hxy = 0.25 * (", "const RFLOAT hxy = 0.5 * (")
elif name == 'no-negdef-guard':     must("if (!(hxx < 0 && det > 0)) return 1;", "if (det == 0) return 1;")
elif name == 'no-offset-guard':     must("if (!(std::abs(ox) <= 1.0 && std::abs(oy) <= 1.0)) return 2;", "")
elif name == 'swap-axes':           must("dx = ox; dy = oy;", "dx = oy; dy = ox;")
elif name == 'global-leaks':        must("experimental_coupled_peak == 2 || (experimental_coupled_peak == 1 && is_global)", "experimental_coupled_peak >= 1")
elif name == 'not-applied':         must("if (verdict == 0) {\n\t\t\t\t\tcur_xshifts[iframe] = posx + dx;", "if (false) {\n\t\t\t\t\tcur_xshifts[iframe] = posx + dx;")
# F3: the hook refuses --gpu unless the arm is 'none'
elif name == 'dc-gpu-refusal-removed': must('if (dc_arm == nullptr || std::strcmp(dc_arm, "none") != 0)', 'if (false)')
elif name == 'dc-gpu-refusal-unset-allowed': must('if (dc_arm == nullptr || std::strcmp(dc_arm, "none") != 0)', 'if (dc_arm != nullptr && std::strcmp(dc_arm, "none") != 0)')
open(p, 'w').write(s)
PY
}
for m in gather-transpose gather-yflip gather-xflip apply-sign apply-y-only-sign drop-hxy sign-hxy half-stencil no-negdef-guard no-offset-guard swap-axes global-leaks not-applied; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target coupled_peak --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $M/build/coupled_peak > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: coupled_peak rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
for m in dc-gpu-refusal-removed dc-gpu-refusal-unset-allowed; do
  mutate $m || { echo "$m: patch failed"; continue; }
  lane cmake --build $M/build --target motioncorr --parallel 8 > $M/build-$m.log 2>&1 || { echo "$m: build failed"; continue; }
  lane $DS_PY -I $M/src/tests/test_dc_hook_gpu_refusal.py --binary $M/build/motioncorr > $M/run-$m.log 2>&1; rc=$?
  echo "mutant $m: CcfDcHookGpuRefusal rc=$rc ($( [ $rc -ne 0 ] && echo KILLED || echo SURVIVED )) $(grep -m1 FAIL $M/run-$m.log)"
done
cp $M/orig.cpp $F
lane cmake --build $M/build --target coupled_peak motioncorr --parallel 8 > $M/build-restored.log 2>&1
lane $M/build/coupled_peak > $M/run-restored.log 2>&1; echo "restored original: coupled_peak rc=$? (must be 0)"
lane $DS_PY -I $M/src/tests/test_dc_hook_gpu_refusal.py --binary $M/build/motioncorr > $M/run-restored-gpu.log 2>&1; echo "restored original: gpu refusal test rc=$? (must be 0)"
