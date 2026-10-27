# Independent review: local all-pairs joint objective on the native CCF capture (Opus, 2026-10-26)

**Verdict.** The proposed raw-half-plane objective J is the exact objective whose coordinate slices the native
CPU local update samples on its integer grid. Its sign, axes, gradient and Hessian are correct, and for this capture
it is numerically indistinguishable (≤ ~1e-33 absolute) from any Hermitian or symmetric-Nyquist variant, because
B=150 suppresses the whole Nyquist row and column. Under careful labelling the diagnostic is feasible. As proposed,
however, it cannot separate "optimizer" from "objective" unless the truth-scoring stage also evaluates J at the
truth-derived trajectory (§4). Sonnet's C9 v1 FAIL stands as recorded. It is a miscalibrated margin rather than an
operator defect, and v2 is not clearance.

## Provenance
- Source: git object `927a6890c8864f81ad58e44eac7281b080714af4` (worktree t3-f9ee0a2b, HEAD 95327ae1);
  `src/motioncorr_runner.cpp` blob `669b3faa…`, extracted copy sha256 `c3e7d526…7e266c`. alignPatch 4884–5163,
  ccfWeightAt 5169, shiftNonSquareImageInFourierTransform 5342.
- Bundle: `…/native-map-bundle-r1/INDEX.json` sha256 `5b3dde3a…c8d3` (verified). Read: metadata, spectra
  (initial/enter/exit/pre-dc/consumed), weights, shifts. **Not read:** `initial-frame*-samples.bin` (pixel payload),
  real maps, peak 3x3, truth. No captured objective value, optimisation or start selection was computed.
- Interpreter: `~/.local/bin/python3 -B -P` (CPython 3.13.7, NumPy 2.4.2); thread variables set to 1; each run < 1 s.
- Artefact hashes: `HASHES.sha256`. Pre-run script hashes: `PRERUN.sha256`.
- Retained failure: `check_opus_v1_run1_FAILED_json_npbool.out`. Run 1 computed every quantity and then failed
  while serialising a numpy bool, so `check_opus_v1_result.json` is a partial file. v2 changes only the two
  `bool(...)` casts and the output name (diff in transcript). Its result is `check_opus_v2_result.json`.

## 1. Derivation (from source)
Native shifter: `shift(F_f, -cur/pn)` multiplies by `exp(+2πi(x·shiftx + ly·shifty))` with ly = y>16 ? y−32 : y, so
F_f ← F_f·exp(−i ω·s_f) with ω = 2π(kx/42, ky/32). For forward-FFT data this moves content by +s_f, so s is the
correction, equal to −displacement.

CCF for frame f: `Fcc_f = (Fref − F_f)·conj(F_f)·W`, with DC zeroed by the #262 hook in this capture (pre-dc DC
≈ 4.0e4, consumed DC = 0, both patches). The map is c2r, unnormalised. With s_0 = 0 as the gauge,

  J(s) = Σ_{j<f} Σ_k m_x W Re[F_j conj(F_f) e^{iω·(s_f − s_j)}] = ½ Σ_k m_x W (|Σ_f F_f(s)|² − Σ_f |F_f|²) = ½ Σ_f c_f(0)

where the last equality uses the raw-half-plane lag-0 sum (m_x = 1 at x ∈ {0,21}, 2 otherwise).

- **Coordinate slice.** Holding the other frames fixed and moving s_f → s_f + r changes J by exactly c_f(r) − c_f(0),
  with c_f the leave-one-out map evaluated with the same raw-half-plane formula. The native integer argmax is
  therefore the argmax of the J slice on the integer lattice within ±15.
- **Native update is not an ascent method on J.** It is a simultaneous (Jacobi) step: every frame moves to its
  slice's 3x3 quadratic-fit peak against the *stale* positions of the others, and the gauge is then re-fixed by
  subtracting r_0. The quadratic fit is not the continuous slice maximiser. A simultaneous step can lower J, and
  the stop rule (rms step < 0.5 px, here after 2 iterations) does not certify stationarity. J at the native
  endpoint will therefore generally be improvable by local polish. Polish alone is not evidence of an optimizer
  failure.
- **Derivatives.** With T_jf(d) = Re Σ Q e^{iω·d}: ∂T/∂d_a = −Σ ω_a Im(Q e^{iω·d}); ∂²T/∂d_a∂d_b = −Σ ω_a ω_b Re(Q e^{iω·d}).
  The Hessian is Σ_{j<f} (e_f − e_j)(e_f − e_j)ᵀ ⊗ ∂²T_jf, which is ≤ 0 at a coherent peak.
- **Invariances.** J is invariant to a common translation of all frames (the gauge) and periodic in each pairwise
  difference with lattice (42, 32). Score endpoints on the torus.
- **The DC term is constant in s.** Zeroing it does not change any argmax or quadratic fit. In the non-hook arm,
  though, the ~4e4 DC offset puts float32 ulps of ~4e-3 into every map value, so the closures below hold only for
  this DC-hook arm.

## 2. Nyquist, R2C self-columns, and what the saved arrays verify
The R2C Hermitian constraints apply only to columns x=0 and x=21 plus the four real corners. Interior y16 entries
are independent stored modes, so raw signed-ky (+16) phase and a symmetric-Nyquist interpolant can differ through
y16 as well as through x21. Quantified from the saved arrays (both patches, `check_opus_v2_result.json`):

| quantity | value |
|---|---|
| saved weights vs float32(formula) | bitwise equal (max abs 0.0) |
| W on column x21 | all 32 entries exactly 0 |
| max W on row y16 | 2.68e-33 |
| (y16 ∪ x21) share of Σ m W \|F_j\|\|F_f\| over initial spectra | 2.1e-34 and 1.4e-34 |
| absolute J bound from those bins; gradient bound (\|ω\| ≤ π) | ≤ 5.5e-34; ≤ 1.7e-33 |
| max \|consumed CCF input\| on y16 / x21 | ≤ 1.1e-34 / 0 |
| Hermitian defect of iter2 C2R inputs (capture's own metric) | ≤ 8.2e-35 |

Consequences:
- At any state, raw-half-plane J and the symmetric-Nyquist trigonometric interpolant of the *exact* pair maps
  differ by ≤ ~1e-33. That bound depends on B=150 at this 42x32 box and is not a general equality: Sonnet's C10b
  exposes a real difference at B=2.
- This does **not** make the interpolant of the *saved float32 real maps* equal to J at fractional shifts. FFTW's
  float32 rounding spreads over every map mode, including unweighted ones, so that interpolant agrees with J only
  to roughly float32 level (~1e-7 relative). Do not equate the two beyond that.
- Generic FFTW behaviour on non-Hermitian input remains unqualified. It is irrelevant here only because the
  measured defect of the consumed inputs is ~1e-34. That is a finite-state measurement, not an FFTW property.
- **Shifter convention, verified FFTW-free** (`check_opus_shifter_v1_result.json`): iter2-enter-fft equals
  initial-fft·exp(−iω·s) with s = iter1-applied-deltas. Max abs diff is 1.5e-8, which is 0.24× a 4-ulp per-bin
  gate. The sign-flip, axis-swap and ky16→−16 mutants miss the gate by 6–8e6×. iter2-enter equals iter1-exit
  bitwise, iter1-enter frame 0 equals initial bitwise, and iter1-enter shifts are zero.

## 3. Parent's finite-state closure: J_actual(F_enter) = ½ Σ_f realmap_f[0,0], abs ≤ 5e-6
The algebra is correct and the closure is worth running, with the following qualifications.
1. **It cannot see sign, axes or ky convention.** At lag 0 no phase enters. Those conventions are now covered by
   the shifter closure (§2), and they enter the argmax grid only at r ≠ 0. Add the per-frame integer-lag closure:
   realmap_f(r) vs Σ_k m Re(consumed_f e^{iω·r}) for every r in ±15, at both iterations and for both patches.
   This ties J's slices to the actual native argmax grid and is sign-sensitive.
2. **Decompose the check** so that a failure can be located:
   (a) per frame, realmap_f[0,0] vs Σ_k m Re(consumed_f), which tests c2r lag-0 semantics only;
   (b) consumed_f vs (Fref − F_f)conj(F_f)W recomputed from enter spectra, which tests float product algebra;
   (c) Σ_f (b) vs the pair form, which tests the J algebra.
3. **Bound.** The magnitude bound on J is ~2.7. A pessimistic float32 c2r error of ~ε·log2(1344)·L1 per map gives
   O(1e-6) summed over 5 maps, so 5e-6 is plausible but sits near the worst case. Record
   L1 = Σ_f Σ_k m|consumed_f| first. It is a magnitude, not an outcome. If L1 makes 5e-6 tighter than ~2× that
   estimate, say so before running. If the closure misses, keep it as FAIL; do not relax the bound.
4. **Negative controls and what each can observe.** Omitting DC zero shifts the result by ~1e5, which is
   discriminating. m_x = 2 at x=0 is probably discriminating; its magnitude is measured at run time and it counts
   only if it exceeds the bound. ky16 sign, x21 handling and Hermitian projection are **unobservable** at lag 0 in
   this capture (W ≤ 2.7e-33). Label them "not observable here", not PASS.
5. **Ideal-phase J(s_enter) vs J_actual.** Given the 1.5e-8 per-bin shifter remainder, this difference will be
   ≲1e-7, below the 5e-6 bound. It is a consistency check that resolves nothing the spectrum-level shifter
   closure has not already resolved more sharply.

## 4. Is the optimizer-vs-objective question well posed?
Only with one addition. The truth-free comparison J(native final) vs J(best of the frozen multistart) can show that
native did not solve J. It cannot show that the maximiser of J is wrong, because a better-J endpoint that is still
inaccurate is compatible with both "J is inaccurate" and "the multistart also missed the true basin". The smallest
correction is a single pre-registered post-optimisation readout, **J(s_truth)**, evaluated after every optimisation
result is frozen:
- J(s_truth) < J(s_best): this patch's objective prefers a wrong trajectory, so stronger optimisation optimises an
  inaccurate objective.
- J(s_truth) > J(s_best) ≥ J(native): optimisation is the binding limitation, and the multistart also failed.

This needs parent sign-off because it extends truth use from "score trajectory error" to "evaluate J at truth".
It also needs a pre-registered truth→s mapping: native sign (s = −displacement), gauge s_0 = 0, relative to the
fixed global G, as the patch-support average over the 42x32 box. Report the within-patch spread of the truth
field, because a rigid s cannot represent a varying field. That spread is a limitation of J(s_truth).

Context for interpretation. Only 18 half-plane bins (30 full-plane modes) have W > 0.01, with |kx| ≤ 2 and |ky| ≤ 3.
The J landscape is therefore a very smooth, low-mode trigonometric polynomial with spatial periods of about 14 px
or more. Secondary maxima ~10 px away, such as the patch-62-79 frame-4 jump (10.13, −8.17) in iter1-applied-deltas,
are structurally expected under heavy noise. Do not treat their existence alone as optimizer evidence.

**Frozen multistart, fixed before any captured outcome.**
- Starts: zero; native final; native iter2-enter (= iter1 result); the 8 frozen PCG64(238267) N(0,2) draws.
- Plus a truth-free lattice applied **symmetrically to every frame** (not conditioned on frame 4, which is singled
  out only by truth error): from native final, displace one frame at a time to each integer offset on a step-5
  lattice within ±15. That is 4 frames × 48 offsets.
- Optimizer: Sonnet's frozen L-BFGS-B settings. Optionally add block-coordinate ascent using the exact slice
  maximum from a 0.25 px dense grid on the torus, which is cheap because the slices are ~30-mode polynomials.
- Report per endpoint: J, ‖∇J‖, Hessian eigenvalues, and torus basin clusters. Freeze everything, then do truth
  scoring (all-5 trajectory error plus J(s_truth)).
- Pre-declare materiality, for example an error change > 0.5 px and a J tie tolerance relative to the L1 bound.
  No hyperparameter or start may depend on truth.

## 5. Sonnet controls: C9 and core
- Core `jointobj_core_v1.py` (sha256 `d331a2a4…`): my independent native-literal implementation (leave-one-out
  product, DC zero, explicit slow raw-half-plane lag-0 sum, synthetic spectra that keep y16/x21 content, B=2)
  agrees with value rel 1.8e-17, gradient vs FD 3.3e-12·Jscale, and Hessian vs FD 1.1e-11·Jscale. Sign, ky
  mapping and axis pairing all match the source derivation.
- **C9 v1 FAIL is real as specified and should stay recorded.** Its two criteria disagree. The prose says "each
  mutant fails the corresponding C2/C5 check" (tolerances 1e-12 and 1e-7); every mutant fails those by ≥ 2e8× and
  ≥ 2.4e5×. The "i.e. ≥ 1e-3·Jscale" threshold is a stricter, different criterion, and the failure is in that
  threshold. Jscale is an L1 magnitude, while J for independent random spectra is a cancelling sum: median |J|/Jscale
  is 0.036 at B150 and 0.010 at B2. Over 200 draws per weight set, the swap mutant changes J by 93–124% of |J| at
  the median, yet 1.5% (B150) and 5% (B2) of draws fall below 1e-3·Jscale. The sign mutant reached 2.3e-5·Jscale
  at B2, so Sonnet's 10 draws were lucky for that mutant. No operator defect is exposed.
- v2 (margin lowered after the result) is a post-hoc amendment and does not clear C9. It is also unnecessary for
  the convention question, which the saved-data shifter closure (§2) now settles with 6–8e6× mutant separation.
  If a synthetic mutant gate is still wanted, pre-register a new v3 rather than amending v1. One suitable form:
  every mutant fails C2 at 1e-12 in every draw, and the median |ΔJ|/|J| is ≥ 0.1.

## Limitations
- Two patches, one movie, the DC-hook arm only, B=150 at a 42x32 CCF box. The Nyquist negligibility and
  Hermitian-irrelevance conclusions do not transfer to other B values or box sizes without re-measurement.
- No certification of global optimality. J(s_truth) uses a rigid-shift approximation of a varying field.
- The saved-map interpolant equals J only to float32 level. Generic non-Hermitian FFTW behaviour is unqualified.
