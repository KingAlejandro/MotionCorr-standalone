# PLAN_PHYSFREQ_STAGE1 (implementation side of the parent's physical-weight screen; HELD, nothing executed)

Parent authority: `/tmp/mc-local-physical-frequency-parent-20261026/PLAN.md` (sha256 in PINS.json) and `SCORING_PINS.json`. This plan only states what the runner does; it adds no hypothesis, criterion or setting.
Status: new post-joint-result, offline weight arm; not a C1 fix, not the global isotropic arm (that harmful control stays untouched/UNRUN); original C9 v1 FAIL retained, v2 relaxation not accepted; no all-controls-PASS and no estimator-qualification claim; native identity/pipeline tests for the changed weight are UNRUN.

## Single changed factor
Local x-frequency denominator 22 -> 42. Everything else is the prior sealed run: same captured float32 initial spectra (`initial-frame{0..4}-fft`), patch window, B=150, signed ky/32 with y=16 -> +16, DC zeroed, complex128 J from the float32 inputs and float32 weights, core `jointobj_core_v1.py` (sha256 d331a2a4...9f36, byte-identical copy, verified at import), L-BFGS-B settings and the 300 s total cap.
`Wphys = float32(exp(-2*150*((kx/42)^2 + (signed ky/32)^2)))`, kx = 0..21 (parent's formula verbatim).

## Run order (script `physfreq_stage1_v1.py`)
1. Release check: JSON binding script, core, this plan, PINS.json, `c9_disposition`, `directional_screen_frozen_sha256`, `authorizes_offline_weight_arm: true`. Without it the script exits.
2. INDEX.json sha256 = 5b3dde3a...c8d3 and per-file size/sha256 on every read; whitelist is only `weights` and `initial-frame{0..4}-fft` of the two patches; no truth path is readable.
3. Sealed baseline JSON sha256 = 5f942ae8...779d; start labels, frozen PCG64(238267) draws and every `s_start` are read verbatim from it and cross-checked (rand starts = the frozen draw, frame 0 = 0). No reseeding.
4. **Weight identity (fail-stop, exit 4)**: the inherited formula (x_norm = 22, native operation order, float64 evaluation since `RFLOAT` = double in the pinned build, cast to float32) must equal all 704 saved weights bitwise on both patches. If not, a `weight_check_FAILED.json` is written and no objective value is computed. No tolerance.
   Reported with it (weight statistics only): bins with W>0.01 / >0.001, W sums, Nyquist row/column maxima for saved-22 and Wphys, and a bitwise comparison of the verbatim Wphys against the same formula in native operation order with x_norm = 42 (diagnostic, not gating, to show how many bins differ only in the last float32 bit if any).
5. 11 runs per patch (zero, native_final, native_iter1_exit, rand0..7) from the baseline starts; reference-point J/gradient/Hessian eigmax at the first three. All outcomes, statuses, caps and a descriptive basin grouping (unwrapped max|ds| < 1e-3 px) are retained. A cap or time stop is recorded, never retried.
6. Candidate = highest J_final within this arm per patch (ties -> earliest label), chosen before any truth. The sealed JSON also carries the baseline candidate verbatim for the parent's paired scoring. Raw J is never compared across arms.
7. Seal: `stage1_outcomes.json` (0444) + `SEAL.json` with its sha256. Truth scoring, patch-mean/spread and J(s_truth) are the parent's, after the seal.

## Not done
No objective or optimizer values for the new arm, no payload read, no baseline rerun, no new controls, no tolerance changes. Scratch is far below 50 MB. After the run I stop and report seal/hashes/statuses only.
