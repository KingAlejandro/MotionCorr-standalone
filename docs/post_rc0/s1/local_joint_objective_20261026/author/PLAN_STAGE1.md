# PLAN_STAGE1 (PROVISIONAL, not frozen; captured optimization HELD)

Status of the prerequisites: controls v1 = C0-C8, C10-C12 PASS, **C9 FAIL** (original margin); v2 relaxation rejected by the parent and not
accepted (see RESPONSE_C9.md, V2_NOT_ACCEPTED.md). Any clearance for the captured run must state the parent's disposition of that C9 failure
(`c9_disposition`), and the plan must be re-frozen after the Opus review. Nothing below has been run on captured data.

## Pins
Source object 927a6890c8864f81ad58e44eac7281b080714af4 (worktree t3-f9ee0a2b). Bundle
`.../Local-CCF-native-capture-r1/native-map-bundle-r1/`, INDEX.json sha256 `5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3`;
every file read is size/sha256-verified against INDEX.json. Patches (62,79) and (62,47), 5 frames, 32x42, half-plane [32,22].
Interpreter `~/.local/bin/python3 -B -P` (3.13.7, NumPy 2.4.2, SciPy 1.17.1), OMP/OPENBLAS/VECLIB/MKL = 1. (`-I` is not usable: it hides the user-site scipy.)

## Objective (definition, signs, derivatives: CONTROL_PLAN.md)
Raw half-plane phase-coherence J(s), DC zeroed, m_x = 1 on x in {0,21} else 2, ky = y>16 ? y-32 : y, F_f(s) = F_f^0 exp(-i2pi(kx s_fx/42 + ky s_fy/32)),
confirmed against the native `shiftNonSquareImageInFourierTransform(F, -cur/pn)` call in the pinned source. Computed in complex128 from the float32 stored spectra.
It is NOT claimed identical to the symmetric-Nyquist trig interpolant of the real maps (C10 exposes the difference on Nyquist-carrying spectra; it vanishes
for Nyquist-free spectra). Weights for the real data are tiny on the Nyquist row/column (native formula, B=150: ~e-33 / ~e-130); the run reports the saved weights' Nyquist maxima.

## Inputs the optimizer may see
initial-frame{0..4}-fft, weights, final-local-shifts, iter1-exit-shifts (+ closure files: iter{1,2}-frame*-{enter-fft,window-fft,real-map,weighted-pre-dc,weighted-api-consumed}, iter{1,2}-{enter,exit}-shifts). The script's whitelist
regex rejects every other path, including anything under `truth`.

## Stage 1 optimizer (provisional settings, as given by the parent)
11 starts per patch, same draws for both patches, in this label order: zero, native_final, native_iter1_exit, rand0..rand7.
rand = `np.random.Generator(np.random.PCG64(238267)).normal(0, 2, size=(8,4,2))` = (start, frame 1..4, [x,y]); frame 0 exactly 0 (gauge; native vectors must have frame 0 exactly 0 or the run stops).
scipy L-BFGS-B on -J, analytic gradient, no bounds, 8 coordinates, `maxiter=300, maxfun=2000, gtol=1e-8, ftol=1e-13, maxls=30`, no restart. Single wall-clock cap 300 s for both patches; capped or unrun starts are recorded, not retried.
Selection: highest J_final over the 11 outcomes per patch, ties -> earliest label; made before any truth exists in the process. No optimality certificate; the Hessian eigenvalues of J at each outcome are reported only as a local-maximum diagnostic.
Per start the JSON stores: s_start and s_final as explicit 5x2 arrays, J_start, J_final, grad inf/2-norm, nit, nfev, njev, status, message, success, hit_cap, time_capped, wall_s, Hessian eigenvalues. Also J, gradient and Hessian eigmax at zero / native_final / native_iter1_exit without optimization. Output is sealed: `stage1_outcomes.json` (mode 0444) + `SEAL.json` with its sha256.

Open scale question for review: `gtol=1e-8` is an absolute bound on the gradient of -J, but the stored spectra are divided by the patch area, so J may be small in absolute terms. The run records grad_inf and Jscale so the ratio can be judged; I have not changed the setting.

## Captured closure requirement (before any optimization; proposed bound, parent/Opus may narrow)
For each captured entering iteration k present (iter1 with s_enter = 0; iter2 with s_enter from `iter2-enter-shifts`, frame 0 exactly 0):
- **A (gating)**: `0.5 * sum_f real-map[f][0,0]` (saved native maps, float32) vs J computed DIRECTLY from that iteration's stored entering F_f (complex128, DC zero), s = 0. Gate: |delta| <= 5e-6 in objective units (the saved maps are unnormalised-C2R units). Raw deltas preserved. If A fails for any patch/iteration, the script writes `closure_result.json` and exits before optimization.
- **B (reported, flagged)**: ideal initial-spectrum J(s_enter) vs J(actual entering F). Same 5e-6 label; B failure is retained and reported, and whether it gates is a parent decision.
- Remainders reported separately: native complex64 expression (float32 products, float64 sum) minus complex128 J, and saved-map sum minus that complex64 value (the C2R/float32 remainder). No FFTW equivalence is asserted.
- Sub-step diagnostics, not gated: saved weighted-pre-dc and weighted-api-consumed vs recomputation; window-fft and initial-fft vs enter-fft bitwise.
- **Vacuity guard (my proposal, not yet agreed)**: a 1 px common perturbation of the entering state must change J by more than 10x the bound, otherwise the 5e-6 bound cannot see state changes and the run stops for a parent decision. The change of |J| for 0.001/0.01/0.1/1 px perturbations is reported as the bound's resolution. At s=0 the sign/swap mutants coincide with J, so this guard, not those mutants, is the closure's sensitivity check.

## Not done, by instruction
No captured numerics read, no optimizer run on payloads, no new controls. `make_fake_bundle_v1.py` (synthetic stand-in layout for a stage-1 dry run) is written but NOT run; whether to run it as a control is the parent's call.
Stage 2 (truth scoring) belongs to the parent (`/tmp/mc-local-joint-objective-parent-20261026/SCORING_CONTRACT.md`) and is not implemented here.

## Revision record
stage1_v1_draft0_unrun.py -> stage1_v1_draft1_unrun.py -> stage1_v1.py (current). None executed on captured data.
