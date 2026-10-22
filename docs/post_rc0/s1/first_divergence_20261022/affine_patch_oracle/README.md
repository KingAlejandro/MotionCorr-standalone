# Affine patch (2,1) known-template oracle, 2026-10-22

Branch `diag/affine-patch-oracle-20261022`, based on reviewed PR278 head
`b12a28ba4c45529f1002baeb0e9bde37e8ccb1ad`. Protocol v1 was committed first at
`c1019f25` (`PROTOCOL.md`, `protocol.json`); results and this note follow in the
next commit. New directory only: no edit to existing evidence, tools, ledger or
source. Offline Mac work, one process, one numeric thread. No SSH, build, native
or GPU work, no push/PR/GitHub/Notion write, no nested agent. Historical totals
stay **2 PASS / 10 FAIL / 4 UNIDENTIFIABLE**; nothing is relabelled and no
native, scientific or performance qualification is made.

## Result

All frozen controls **PASS** and all eleven mutants were rejected by the frozen
gates (attempt02); the control power behind that statement is qualified under
"Corrections after review R1" below. The oracle recovers the patch geometry exactly, shows that a
pure-translation ideal-template oracle is **INVALID** for this window, and splits
the native patch update into separate terms. The #276-validated fit is **UNRUN**:
one patch cannot cover its lattice.

- **Geometry (PASS).** Patch (2,1) is a hard 42×32 crop, X `[0,42)` Y `[32,64)`, of the
  real-space frame after the *global* Fourier shift by the final global state. The
  captured global iteration-1 spectra plus each backend's `state/global.txt`,
  pushed through the native shift formula in double, reproduce the captured
  patch input to relative L2 (excluding DC) **2.1e-5** worst case (gate 1e-3). The
  seven wrong-geometry mutants (shift sign, x↔y, crop ±1 px in x and y, wrong
  patch, role-swapped crop, no pre-shift) score 0.24 to 1.5, at least 11 000×
  the baseline. DC is 99.9969 in capture and reconstruction.
- **Truth is an interval, not a number.** Under the native state the shift that
  would align a window pixel varies linearly over the window; its range is
  0.74 × 0.56 px (x × y) at frame 4 (0.19 × 0.14 at frame 1), predicted before
  computing. Window-crop control: a pure analytic translation of the same window
  already gives estimates off by up to 1.22 px (true `(0,-2)` → `(-0.58,-0.93)`;
  true `(0,-0.5)` → `(-0.15,-0.22)`), so the pure-translation oracle fails the
  frozen validity rule on both counts. The point reference is therefore `R_fm`, the
  continuous maximum of the production-weighted CCF between an independently
  rendered deformed window and the target window (an objective maximum, not
  injected-motion truth).
- **Input is not the problem at iteration 1, for the fixed-template objective.**
  Native input versus the independent render changes the fixed-template maximum
  by ≤ 0.001 px (float32 contribution ≤ 1e-5 px). Later iterations and the
  sum-of-others objective were not tested this way. The
  analytic render, which has no global Fourier shift, differs from the captured
  spectra by up to 0.9% of the AC spectrum; this is attributed to the global shift
  of non-periodic frames (edge ringing) but not isolated.
- **Dominant terms of the native iteration-1 update** (norms in px, frames 1–4;
  `summary.txt`, identity residual 1e-16):

| Term | CPU | CUDA |
|---|---|---|
| native − truth(centre) | 0.52 0.72 1.15 0.76 | 0.46 0.30 0.39 0.37 |
| native candidate − parabola on the double map (CPU frame 0: different lattice point, see below) | 0.44 0.48 0.50 0.49 | 0.03 0.13 0.07 0.06 |
| separable parabola vs continuous maximum | 0.27 0.19 0.40 0.31 | 0.35 0.25 0.29 0.45 |
| sum-of-others vs fixed template | 0.11 0.06 0.13 0.11 | 0.13 0.10 0.11 0.18 |
| native input vs independent render | ≤ 0.001 | ≤ 0.001 |
| `R_fm` − truth(centre) | 0.23 0.27 0.56 0.38 | 0.24 0.03 0.23 0.04 |

  The CPU term is a **frame-0 anchor effect caused by an exact float32 tie**. At
  iteration 1, frame 0, lattice points `(-1,0)` and `(0,0)` are exactly equal in
  both backends' float32 maps (`exact_ties = 2` in `attempt02.json`); in double
  their gap is 0.49 ULP (CPU) and 0.53 ULP (CUDA). The CPU row-major strict-maximum
  scan keeps `(-1,0)`, the CUDA lane reduction keeps `(0,0)`, so the backend
  difference here is the tie rule. On the CPU the separable parabola, centred on a
  different lattice point, moves frame 0's y candidate by about +0.49 px through
  the peak's cross-term (Hessian condition ratio about 3.7); float32 rounding at
  the same winner adds about −0.05 px (y) and −0.09 px (x). The last two numbers
  are the reviewer's, from a control not rerun here. Anchoring then moves every
  frame by frame 0's candidate difference (0.45 px; per-frame terms are ≤ 0.08).
  CUDA frame 0 has exact ties at iterations 1–5 and frame 1 at iteration 3 (all
  winners `(0,0)`). The float map is within 2.4 ULP of the double map (attempt02,
  iteration 1) while the peak curvature is only 5.6/7.5 ULPs in x/y, which is why
  sub-pixel candidates scatter by 0.1–0.6 px even without a winner flip (CUDA
  iteration 2: 0.19–0.32 px, no flip).
  The `R_fm` − truth term splits (post-hoc) into a window-only part (up to
  0.61 px CPU, 0.26 px CUDA) and a deformation-only part ≤ 0.055 px, so on this
  signal the finite weighted window, not the affine deformation inside it,
  accounts for most of the gap between the objective maximum and the centre truth.
- **Acceptance differs between backends; the cause is not isolated.** CPU patch (2,1) converges at iteration 2
  (RMSD 0.569, 0.301) and enters the fit; CUDA never does (0.574, 0.673, 0.730,
  0.778, 0.781; both captured attempts byte-identical) and is excluded. RMSD values
  equal the retained logs within their print precision (`supplement02`). Replaying
  the *same specified algorithm in double* from the captured iteration-1 input gives
  the opposite outcomes: CUDA-state input converges at iteration 2, CPU-state input
  does not converge in 5 iterations (50 iterations at 1e-9 also not). Each
  backend's decision is therefore sensitive to float32 quantization and tie
  behaviour on its own input. The two backends enter patch alignment with
  different global states (frame 4: CPU `(-2.886, 1.754)`, CUDA `(-3.448, 2.450)`)
  and different patch inputs, and no arm runs both backends' float32 arithmetic or
  tie rules on the same input, so the CPU/CUDA accept/exclude difference is not
  attributed to arithmetic rather than to the different global trajectories. With an exact maximum
  the sum-of-others iteration converges to `R_fm` (≤ 0.003 px).
- **Native states versus references** (last captured iteration, norm px, frames
  1–4): CPU to `R_fm` 0.15 0.22 0.34 0.18, to centre truth 0.34 0.45 0.90 0.56;
  CUDA to `R_fm` 0.41 0.42 0.50 0.32, to centre truth 0.50 0.43 0.41 0.28. Even the
  exact-maximum floor stays 0.23–0.56 px (CPU state) and 0.03–0.24 px (CUDA state)
  from the centre truth; the window part depends on the residual shift left after the
  global stage, which differs between the backends. These are descriptive; no field
  metric is computed.
- **Fit (UNRUN).** Native needs more than 18 observations; accepted patch (2,1)
  gives 5 rows (CPU) or none (CUDA). The minimal missing capture is in
  `future_native_capture_manifest.json` (16 short processes reusing the verified
  #275 binaries, no source change); it is a proposal and nothing was launched.

## Pre-registered expectations and outcomes

| Expectation (frozen before results) | Outcome |
|---|---|
| G-W, G-R, G-M, G-N, G-X, G-E, G-CS, PC, WC-zero PASS | all PASS (weight 6e-8; render ≤ 3.8e-6, generator cross-check 5.7e-14; continuous map 1.1e-15 of peak; candidate replay 0 / 2e-8 px; 36 CUDA c2/c3 files identical; baseline 2.1e-5; sign-check ratios 0.04–0.08 vs 0.5; periodic control continuous error ≤ 3.3e-8 px, integer parabola 3e-10 px) |
| N-E1..N-E7 (geometry) and N-C1..N-C4 (comparator/render) all rejected | all rejected; the 11 467 to 72 114× separations belong to N-E only (see review R1 F2 below) |
| pure-translation oracle INVALID (frame-4 range about 0.74 / 0.56 px) | INVALID: range max 0.736 px, window-crop bias up to 1.22 px |
| fit UNRUN | UNRUN |

Not predicted and found after reading results (post-hoc, `supplement01`): the
frame-0 anchor flip, the window/deformation split, per-iteration quantization
(CUDA iterations 3 and 5 flip a winner; anchored native-versus-double differences 0.12–0.62 px over iterations 2–5) and the
double-precision replay outcomes. Fractional-offset parabola error in the
*periodic* control is 0.12–0.32 px (separable parabola bias in this geometry),
reported not gated.

## Attempts and failures

| Attempt | Exit | Note |
|---|---|---|
| `attempt01` | 1 | retained: crashed before output; the script assumed the CPU per-frame map file names for the CUDA capture, which stores one concatenated `map.bin` |
| `attempt02` | 0 | loader fixed, nothing else; script identical to `affine_patch_oracle.py` |
| `supplement01` | 0 | post-hoc splits and double replays from `attempt02.json` (its script block text is exec'd verbatim and hash-checked) |
| `supplement02` | 0 | post-hoc log RMSD check |

`attemptNN.argv/log/exit` hold the exact commands and outputs. `summarize.py` →
`summary.txt` prints the table above. `artifacts.json` binds every file here by
SHA-256.

## Provenance and resources

Inputs read in place and hash-verified through `file-index.json`
(`31255dab…`, equal to the committed #275 receipt index at `6ae48678`):
`fixtures/affine.mrcs`, `affine_target.npy`, `affine_field.npy`, MANIFEST
(`9697c203…`), `runs/{cpu,cuda}-affine-on/capture/c1*`, `c2*` and `state/global.txt`,
plus the two logs. The CUDA attempts `c2` (batched) and `c3` (full retry) compare
byte-identical, 36 files. Every bound hash is in `attempt02.json`. The forward model
is written from the generator's constants (not imported) and checked against the
generator's functions at 1000 points (5.7e-14), against the stored frames
(3.8e-6, half a float ULP at 100) and field (exact).

Mac 14 CPUs, load ≈ 3.8 with no competing numeric process; Python 3.13.7, NumPy
2.4.2; `OMP/OPENBLAS/VECLIB/MKL_NUM_THREADS=1`; scratch `/tmp/motioncorr-affine-patch-oracle-*`
(< 1 MB); run time 0.15 s. No timing is claimed. Production `src/` is untouched; the `attempt02` script SHA-256 is in its JSON.

## Limits

- One affine realisation (128×96×5, B = 150, no noise), one patch of nine, two
  backends each with its own global trajectory. Nothing here supports a claim about
  other patches, noise, other fixtures or other backends.
- "Window bias" is the production-weighted CCF (hard 42×32 crop, B = 150, `nx/2+1`
  weight normalization, search ±15) on this one low-frequency signal; the weight and
  the crop were not varied, so their separate shares are untested.
- The double-precision replays are references on captured float32 spectra, not
  native alternates; the exact maximum and the replay arms are counterfactuals,
  not proposed estimators. The weight, estimator, stopping rule, defaults and
  gates remain HELD (#279/#280/M4/M5) and none is proposed here.
- The truth interval and `R_fm` are patch-level; no fitted-field comparison was made,
  so the affine field gate FAIL (0.455 / 0.323 px) is not explained or changed.

## Recommended next bounded action

Parent decides, in this order: (1) authorise the 16-process capture in
`future_native_capture_manifest.json` under the usual locks (no source change,
correctness only), then run the generalised oracle per patch and, if at least four
patches are accepted, feed the observation table to the #276 fit path; (2) record
the window-crop finding and the frame-0 anchor sensitivity on the held #279/#280
questions without changing any default.

## Corrections after review R1 (summary-only; no recompute)

Independent Opus review R1 (`review/round1/REPORT.md`, SHA-256
`b5a5f4f7…8d05`) reproduced `attempt02` and `supplement01` and found no blocker for
a draft evidence packet; its four findings are applied as wording only
(`review/round1-response.md`). Results, labels, scripts, protocol, the failed
attempt and `artifacts.json` are unchanged. Consequences for how to read the
sections above:

- **Control power (F2).** N-E1..N-E7 are geometry mutants and carry the stated
  separations. N-C1..N-C3 change only the expected value and N-C4 renders the frame
  with the opposite sign, so none of them mutates the estimator; they show that the
  comparator reads the right field. The estimator path is constrained against native
  data by G-N (native candidate replay ≤ 2e-8 px) and the float-versus-double map
  agreement (≤ 2.4 ULP at the peak, iteration 1). The reviewer measured G-E to cross
  its 1e-3 gate at a global-state error of about 0.003 px (x) and 0.005 px (y), and
  0.26 with the other backend's state; so G-E pins geometry and state far more
  tightly than the ±1 px mutants show.
- **G-CS (F4).** It compares the oracle's render with its own inverse map and cannot
  detect an error they share. The sign witness against native data is the
  native-input-versus-render agreement (≤ 0.001 px) together with G-E.
- **Ties (F1).** The frame-0 effect is an exact float32 tie resolved by different
  scan rules, amplified by the separable parabola's cross-term.
- **Backends (F3).** The backend acceptance difference is confounded with different
  global states and is not isolated.
- Reviewer observations kept as open items: the window bias (0.24–0.61 px) is of the
  same order as the retained affine field-gate FAIL (0.455 / 0.323 px) but nothing
  here claims it explains that FAIL; the window share is not separated into crop,
  weight and content periodicity; the reviewer's control `C2b` is ill-posed and is
  retained, not used.
