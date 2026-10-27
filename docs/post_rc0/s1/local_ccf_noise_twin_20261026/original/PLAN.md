# PLAN (frozen before any bridge or twin computation)

Agent: Sonnet 5.5 (`claude-sonnet-5-5`), effort high, bounded saved-data worker. Date 2026-10-26.
Scratch: `/tmp/mc-local-ccf-noise-twin-bridge-20261026` (<= 50 MB). No repo edits, no native build, no alignment/movie producer, no GPU/CI, no source/default/gate/threshold changes.
Interpreter: `/Users/alex.konstantinov/.local/bin/python3 -B` (NumPy 2.4.2), `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=VECLIB_MAXIMUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`.
Status of the question: auxiliary counterfactual diagnosis. Not native/science qualification, not truth-guided estimator selection. All historical gates remain FAIL.

## 1. Question and single factor
At retained noisy K267 patches (62,79) [bad] and (62,47) [central], alignPatch iteration 1 frame 4: does the sign of each reference's conditional objective gap
`D_j = I_j(x_nat) - I_j(x_phys)` (j = 0..3, plus the aggregate) persist when additive pixel noise is removed, with the captured global trajectory G, global-shift/crop operator, patch geometry, B-factor weight and evaluation points all held fixed?
One factor: input movie noisy.mrcs -> noiseless affine.mrcs. No noise-seed grid, weighting/window/reference change, new frame counts or extra experiments.

## 2. Pinned inputs
- Capture source commit `927a6890c8864f81ad58e44eac7281b080714af4` (read from git objects of `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9ee0a2b`; root checkout not used). Blobs extracted to `src/` (git blob / sha256):
  - `src/motioncorr_runner.cpp` 669b3faa92cb6584980d0e14474fd6a2af0ca863 / c3e7d526db6a861f19680111df7932467e39b18077a424446f886b8aff7e266c
  - `src/jaz/single_particle/new_ft.cpp` 7b9f98ad8bdcc7a23aa8773c56e2707e4875a855 / 0591a2130256053e5739f613374adcb043517d7306dd370849b1468dd6455991
  - `src/jaz/single_particle/new_ft.h` 257ac366d37fda2d1aa81db9c77bac912de62f86 / 803ce749ebbe26933ad84856423285e9ab7ed12a1db429b2ef599c8cf4f77eff
  - `src/local_ccf_capture.h` 799d194926d954cd0e0f49e68d97a1c3c41e9174 / a0ab50de30b23173ba9b6ee99ecd1715b39a2c7111fde8a3f37f6700baffc40a
  - `test-data/generate_motion_diagnostics.py` 8e6accca8d0cc26c1559d4411ac06311138a020e / 5e781bb290b3f12b38f6dc7ec18bb955d56331219dc0216321e010ecbcdaf4cc
  - `test-data/generate_known_motion_fixture.py` 387bd4fe8ff5456ddea293fee78f3d1d40b4f49d / f28fbf516f8c2f7a3ae1b6133d54d3cc1e0708e2f90644cce30a845f4bbcef4f
- Primary sealed capture 63d73581699aebfba6d95c0f730b32434b22858f; pairwise review base 3112458b (context only).
- Capture bundle: `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1`, `INDEX.json` sha256 5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3 (re-verified at run time; every consumed file is also checked against its INDEX.json sha256).
- Truth (scoring only, never in a peak chooser): `capture-bundle-r1/truth-scoring-only/{MANIFEST.json (sha 9697c203...ad02dc), noisy_field.npy (sha 839c484f...5799)}`.
- Movies: pinned digests noisy 5000fbfc0d87cb4be7a8197685297176a2200f9c0d1866f94a7202aa5e85dab3, affine 1cf918d5da48d4c746020983017222829db9c949e362d07169a823bdc118260a (from MANIFEST). Exact-hash local copies exist (`/private/tmp/q268-fix-brIo/md/{noisy,affine}.mrcs`, 246,784 B each; also in many other /private/tmp dirs). Copied to `inputs/` and re-hashed. **No SSH to cpu64 was used or needed.** No regenerated movie is substituted for a pinned input.
- Prior numerics (context, correct per parent review; the original section-3 "wrong G values" and causal-window claim are NOT adopted): `/tmp/mc-local-ccf-pairwise-ref-20261026/{PLAN.md,RESULT.json,REPORT.md,pairwise_ref_analysis.py,SHA256SUMS}`. Its saved-state gaps for patch (62,79): +.038256127285, +.015335707995, +.000159011673, -.014874256971 (j0..3); aggregate native point-minus-physical +0.0388765339324812.
- Fixed G (verified bit-exact against `global-shifts.bin` at run time): f0 (0,0); f1 (-.604719206927727, .5450050278665695); f2 (-1.0768416731350752, .7762553844192274); f3 (-1.7222530225852142, .8919129738766326); f4 (-2.2801393506129037, .5656077519907101).

## 3. Twin verification (before any twin value is computed)
From the pinned generator and manifest, without assuming twinhood:
1. `recipe(noisy)` and `recipe(affine)` must differ only in `noise` (4.0 vs 0.0) and `role` (not used by `render`); `motion`, `signal`, `seed`, `pedestal`, `contrast`, `nx,ny,frames` identical.
2. `noisy_field.npy`/`affine_field.npy` manifest hashes and `*_target.npy` hashes equal (truth/scene identical).
3. Noise-term check: regenerate only `n = Generator(PCG64(238262)).normal(0, 4.0*1.0, (5,96,128))` (stream convention from `render`) and require `noisy_f32 - affine_f32 == n` to float32 rounding, i.e. `|noisy - affine - n| <= spacing(|noisy|)/2 + spacing(|affine|)/2` elementwise (rigorous rounding bound; not a tuned threshold). Report mean/std of the difference. A failure is reported as a failed twin precondition and stops the twin claim.
4. Header/layout check of both MRCs (1024 B header, mode 2 float32, nz=5, ny=96, nx=128, [z][y][x]) against `write_mrc_stack`.

## 4. Source-pinned bridge (NumPy), operator from the pinned source
Native pipeline for this run (`--use_own --skip_defect --bin_factor 1 --group_frames 1 --patch_x 3 --patch_y 3 --max_iter 5`, no gain, no dose weighting before local alignment, CPU, RFLOAT=double):
1. Read frames float32 [5,96,128] (no hot-pixel/defect step: `skip_defect`).
2. Global forward r2c per frame, divided by 96*128 (`NewFFT::FwdOnly`).
3. Global alignment accumulated `G`; each iteration applies `shiftNonSquareImageInFourierTransform(F, -dx/128, -dy/96)` to frames 1..4 (phase `exp(2*pi*i*(kx*(-dx/128) + ky*(-dy/96)))`, `kx=0..64`, signed `ky` with `ky=+48` at Nyquist, double-precision sin/cos, product cast to float32). Frame 0 unshifted. The per-iteration deltas of the global alignment are NOT retained, so the bridge applies the single total `-G/pn` phase ramp (documented difference vs. the native multi-step float32 accumulation).
4. Global inverse c2r, unnormalized -> real frames. The shifted spectrum is not Hermitian at x-Nyquist (and y-Nyquist row); FFTW c2r ignores the imaginary part of the self-conjugate/Nyquist-column terms. NumPy `irfft2` (c2c over axis 0 then c2r over axis 1) is used and is **tested, not assumed**, to match (see §5).
5. Patch clip, extents x[42,84), y[32,64) for (62,47) and x[42,84), y[64,96) for (62,79) (from `patch.json`), group = 1 frame so no summation. Samples [32,42] float32.
6. Patch r2c, divided by 1344 -> `F_j` [32,22] complex64. CCF geometry from `fft-config.json`: no cropping (ccf 32x42), weight = captured `weights.bin`.
7. alignPatch iteration 1 (all shifts zero at entry): `Fref = sum_j F_j` (float32, j order 0..4), frame 4 cross-spectrum `S = ((Fref-F4)*conj(F4))*W`, `S[0,0]=0` (DC arm), C2R unnormalized -> real map `M` [32,42].

Two bridge arms are fixed in advance and both reported:
- **B32** (closest to native storage types): float32 storage at every stage native stores float32 (raw frames, `F`, shifted `F`, real frames, patches, patch `F`, `Fref`, products), float32 pocketfft, phase ramp computed in float64 then cast per native expression.
- **B64**: same operators in float64 from the float32 movie values.
Neither is tuned after seeing results. Technical repairs (e.g. an index or layout bug) are versioned as `bridge_v2.py` ... with the failed attempt and its errors kept in `ATTEMPTS.md`; conventions (sign, norm, Nyquist treatment) are not changed to improve agreement.

## 5. Noisy-control state reproduction (Phase A; no twin number computed or printed)
For both patches, frames 0..4, both arms, report max abs / RMS / relative error vs captured arrays at each stage: `initial-frame{j}-samples`, `initial-frame{j}-fft` and `iter1-frame{j}-window-fft`, `iter1-reference`, `iter1-frame4-sum-of-others`, `iter1-frame4-raw-product`, `iter1-frame4-weighted-pre-dc`, `iter1-frame4-weighted-api-consumed`; plus actual G, window/extents, sample->FFT linkage (captured samples through the bridge patch FFT vs captured FFT), and engine check: captured `iter1-frame4-real-map` vs `irfft2(captured consumed S)*1344` (NumPy vs native FFTW c2r, incl. Nyquist handling). Hermitian residuals of the shifted global spectra are reported. Errors are preserved even when large.

**Explicit propagation bound** (no tuned threshold). The objective is linear in the spectrum: with `c = fft2(M)/1344` equal to the Hermitian-completed spectrum `Ŝ` (columns kx=0 and kx=21 projected `(S[ky]+conj S[-ky])/2`, columns kx=1..20 counted twice), `f(x) = Re sum_k Ŝ_k β_k(x)` with `β_k = b_y b_x`, `|β_k| <= 1` (symmetric cosine Nyquist splitting as in the original). So
- `|Δf(x)| <= sum_k |ΔŜ_k|` (full-grid Hermitian L1),
- `|Δgap| <= sum_k |ΔŜ_k| · |β_k(x_nat) - β_k(x_phys)|` (<= 2·L1),
where `ΔS` is bridge-minus-captured cross-spectrum (aggregate, and each pairwise `S_j = F_j conj(F4) W` formed in float64 from bridge vs captured `F`). The cross-product form `|ΔS_j| <= W(|ΔF_j||F4| + |F_j||ΔF4| + |ΔF_j||ΔF4|)` is evaluated per bin as a consistency check that can fail. The engine term is `B_eng = sum_k |ĉ_native-map - ĉ_irfft2(captured S)|` (and the same weighted by |β_nat-β_phys|). Measured `Δgap` is reported next to every bound.
**Controlled-state criterion** (a resolution statement, not a pass of any science gate): the control is "controlled" iff `B_total = B_state(agg) + B_eng` (gap-weighted) is smaller than the captured aggregate gap `0.0388765339324812` (so the sign of the quantity under study is resolvable), and the bridge reproduces the captured pairwise gaps to within their own measured bounds. Per-component resolution is judged individually: a component with `|D_j| <= B` is reported UNRESOLVED. If the criterion fails, STOP; deliver the exact unresolved precondition and no twin claim. The code enforces this: the twin phase refuses to run unless the Phase-A result JSON records `controlled=true`.

## 6. Twin (Phase B), only if Phase A is controlled and §3 passes
Change ONLY the input movie (noisy -> affine) through the identical bridge arm(s), same G, geometry, weights `W`, evaluation points (`x_nat`, `x_int`, `x_phys` taken from the captured noisy run and NOT recomputed per arm), original weight with DC zeroed.
- Scoring: original trigonometric interpolant (`trig_eval`, symmetric cosine Nyquist split), fixed points per patch: `x_nat = iter1-frame4-peak.raw_selected_xy_ccf`, `x_int = integer_xy`, `x_phys = (truth[4,cy,62]-G[4]) + iter1-frame0-peak.raw_scaled_xy_movie` (observed aggregate frame-0-gauge physical point, as original), `x_truth_unanchored`, per-reference true relative shift `truth[4]-truth[j]`, and an arm-local stationary candidate refined from `x_nat` (descriptive). Truth only evaluates fixed points; it never selects a peak.
- Components analysed: 8 = patches {(62,79),(62,47)} x references j {0,1,2,3} at iteration 1 frame 4, plus aggregate. Report `I_j(x_nat)`, `I_j(x_phys)`, `D_j`, integer-point and nearby-choice gaps, closure `sum D_j` vs aggregate, for noisy-control and twin arms.
- "Remote-basin preference persists" for component j means `D_j > 0` in the twin. Sign flips, magnitude change, and UNRESOLVED (within bound) are reported separately. The twin interval uses `B_twin = B_ctrl + |gap(B32) - gap(B64)|_twin`, assuming float32-rounding error magnitude on the twin equals that measured on the control (rounding is absolute and the pedestal is shared); this assumption is stated, not measured, since no native twin exists.
- Optional descriptive only: native-rule integer maximum in the strict box [-15,15]^2 (strict `>`, y outer, x ascending) for aggregate and each pairwise map, with tie counts. No 32x full-grid/global/Newton broad search, no temporal-reference pruning, robust fit, iso-weight threshold or model adoption.

## 7. Scope guards
Max 2 patches, 5 frames, no extra native producers or continuations, no external publication. Prior artifacts are not modified. Pairwise maps for individual j are auxiliary regenerated NumPy maps (native FFTW c2r ran only on the aggregate); the primary real-CCF-map remains the captured native map. No global optimality certificate (`UNPROVEN_GLOBAL`). No generic invalid-C2R-extension assumption.

## 8. Deliverables
`PLAN.md` (this, hash recorded in RESULT), `bridge_v*.py`, `RESULT_control.json`, `RESULT_twin.json` (or a stop record), `REPORT.md`, `ATTEMPTS.md`, `COMMANDS.log`, `SHA256SUMS`, model provenance. Measured vs UNRUN explicitly separated; one concrete conclusion or blocker.

## 9. Clarifications fixed before any computation (C1-C3)
- C1. The controlled-state gate is evaluated per bridge arm on the bad patch (62,79) against its captured aggregate gap `0.0388765339324812`. The central patch (62,47) is the comparison: its own bound and resolution status are reported but it does not gate the twin.
- C2. Per bridge arm, the twin is run only for arms that satisfy C1; arms are never switched or merged after seeing twin values. If both arms are controlled, both are reported and the conclusion requires them to agree in sign for each component, else that component is reported UNRESOLVED.
- C3. Pairwise maps `I_j` (j=0..3) are float64 NumPy `irfft2(S_j, norm='forward')` regenerated maps in every arm (auxiliary; native c2r ran only on the aggregate). The aggregate map of an arm is the arm's native-like chain (B32: float32 `Fref`, product, c2r; B64: float64). The captured native aggregate map is the primary reference and is only available for the noisy movie.
