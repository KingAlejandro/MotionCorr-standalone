# Affine patch (2,1) known-template oracle: frozen protocol v1

Frozen 2026-10-22 on `diag/affine-patch-oracle-20261022`, based at reviewed PR278
head `b12a28ba4c45529f1002baeb0e9bde37e8ccb1ad`. This file and `protocol.json` are
committed **before any oracle result exists**. Nothing here changes production
source, defaults, weights, estimator, gates or tolerances, and no new acceptance
gate for MotionCorr is created. All numeric limits below judge the *oracle's own
controls*; the MotionCorr measurements are reported, not gated.

## What was looked at before freezing

Source reading only: `src/motioncorr_runner.cpp` (`alignPatch`, patch bounds,
`shiftNonSquareImageInFourierTransform`, fit), the #275 overlay (`capture.h`,
`diagnostic.patch`), `test-data/generate_motion_diagnostics.py`, the #276 fit-oracle
README, the PR278 packet and its two reviews, and issues #238/#279/#280 (read-only).
Also seen: the `file-index.json` hash (matches the committed #275 receipt index),
capture file names/sizes, `c1.json`/`c2.json` metadata, the CPU/CUDA
`state/global.txt` values and the native log RMSD lines for patch (2,1). No
patch-level number of this protocol was computed.

## Geometry and conventions recovered from code (not inferred)

- Patch (2,1) is 1-based (y,x) = row 2, column 1 of the 3×3 grid: window
  X `[0,42)`, Y `[32,64)`, size 42×32, 0-based pixel-index coordinates
  `u=(x,y)` with pixel centres at integers. The logged centre `(20,47)` is
  integer division; the geometric window centre is `(20.5,47.5)`.
- The window is a hard rectangular crop (no taper, no padding) of the
  **real-space globally pre-shifted frame**: global Fourier shift of the full
  128×96 frame by the final global state, inverse transform, crop, forward R2C
  transform of the 42×32 crop normalised by `1/(42·32)`; groups are single
  frames (5 groups).
- State convention: shift `s` is the displacement of frame *content* needed to
  align it to the reference. The Fourier shift multiplies bin `(kx,ky)` by
  `exp(-2πi(kx·s_x/nx+ky·s_y/ny))` (`ky` signed, Nyquist row at `+ny/2`); it moves
  content by `+s`. The CCF is `IFFT[Fref·conj(F_f)·w]`; its peak at `d` means
  content of `F_f` moves by `+d`. Patch iteration-1 state starts at 0.
- Weight `w(y,x)=exp(-2B((ly/nfy)²+(x/nfx)²))`, `B=150`, `nfx=nx/2+1=22`, `nfy=ny=32`
  (the inherited formula, checked only for fidelity). Search `±15`; separable
  3-point parabola through the CPU row-major strict-maximum integer winner;
  anchoring subtracts frame 0's candidate; RMSD test `<0.5` px, at most 5
  iterations; a patch that does not converge is excluded from the fit.
- Generator: frame `f` shows target content at `q` at `p=forward_f(q)=q+g_f+A_f(q-c)`,
  `c=(64,48)`, `t=f/4`, `g_f=(3.25,-2.125)t`, `A_f=t[[.012,-.008],[.006,-.010]]`;
  `field_f(q)=q-forward_f(q)`. Frame 0 equals the target. For globally pre-shifted
  content (shift `+g^nat_f`) the pixel at `u` shows target content at
  `q=inverse_f(u-g^nat_f)`, and the pure-translation shift that would align it is
  `s*_f(u)=field_f(q)-g^nat_f`. This varies linearly across the window.

## Which stages can be judged against injected motion

| Stage | Reference | Judged against injected motion? |
|---|---|---|
| E: extraction + global pre-shift + forward FFT | independent double reconstruction; analytic render | yes, exactly (pixel data are fully determined) |
| C: weighted same-state CCF map | double map from the same spectra | against the objective, not truth |
| P: peak estimate and acceptance | continuous maximum of the same double objective | against the objective, not truth |
| T: truth | `s*_f(u)` | **only as an interval**: the window holds a deformation, so no single injected number exists |
| F: #276 polynomial fit | needs the lattice | **UNRUN** (see Fit) |

Validity rule for a pure-translation ideal-template oracle on this window
(frozen): VALID only if, for every frame 1–4 and both axes, the range
`max-min` of `s*_f(u)` over the 42×32 pixel grid is ≤ 0.05 px **and** the
window-crop control biases below are ≤ 0.05 px. Otherwise INVALID, the truth
reference is reported as `[min,max]` plus the value at the geometric centre
`(20.5,47.5)` (and at `(20,47)` for the logged centre), and the point reference is
the continuous maximum of the production-weighted CCF between the analytically
rendered deformed window and the analytic target window (`R_fm`; "objective
maximum on an independently rendered forward model", not injected-motion truth).
Expected from the generator constants before computing: INVALID for all frames
(range at frame 4 is about 0.74 px in x and 0.56 px in y).

## Computation (one script, Mac, NumPy only, one numeric thread)

1. **Provenance.** `file-index.json` must hash to
   `31255dab8eef81ee05f68271ac665429db9a48498b240fbe85ebe228ea3c65c3` and equal
   `array_product_index_sha256` of the committed #275 receipt index
   (`git show 6ae48678:docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json`).
   Every input read is verified against `files[...]['sha256']`; the fixture
   MANIFEST must be `9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc`.
2. **Independent forward model** written from the constants above, not imported
   from the generator; cross-checked against `generate_motion_diagnostics.py`
   functions at 1000 fixed points (≤1e-12) and against the stored target, field
   and frames (render vs stored float32 frames ≤ 1e-5; field vs closed form ≤ 1e-12).
3. **Stage E.** For CPU and CUDA separately: take the captured global
   iteration-1 input spectra (`c1-i1-input`), apply that backend's own
   `state/global.txt` with the native phase formula in double, `irfft2`, crop,
   `rfft2/(42·32)`; compare per frame with the captured patch iteration-1 input
   (`c2-i1-input`). Also: the same chain from the double FFT of the stored mrcs
   frames, and the analytic render of the window with no Fourier shift. Report
   `rel_ac`, the relative L2 difference excluding bin (0,0). Report the
   edge-ringing contribution (analytic minus pipeline) separately from the
   float32 contribution (pipeline minus capture).
4. **Stage C/P.** Continuous maximum by Newton iteration on the exact
   band-limited CCF (analytic gradient and Hessian, start at the integer winner,
   at most 50 iterations, stop when the gradient norm is below 1e-12 times the
   peak value). The continuous map is checked against `irfft2` samples at all
   lattice points (≤1e-9 of the peak). Compute for CPU, CUDA (captured attempts
   `c2` batched and `c3` full, which must be byte-identical), reconstructed and
   analytic inputs: sum-of-others map and fixed-template map (template =
   native frame-0 patch for captured/reconstructed inputs, analytic target window
   for the analytic input); integer winner, tied maxima count, parabola estimate,
   continuous maximum, Hessian eigenvalues and condition ratio; compare the
   double map and parabola with the captured float32 map and captured candidate;
   replay the native acceptance rule (RMSD per captured iteration, `<0.5`) from the
   captured candidates and compare each captured state with `R_fm`, `s*` band and
   centre values.
5. **Decomposition** (iteration 1, state 0, vector per frame, fixed telescoping
   order): `native − truth_centre = (native − b) + (b − c) + (c − cT) + (cT − d) + (d − t)`
   with `native` the captured anchored candidate, `b` the parabola on the double
   sum-of-others map of the captured input (quantization/tie term), `c` its
   continuous maximum (parabola-estimator term), `cT` the continuous maximum of the
   fixed-template objective on the captured input (sum-of-others blending term),
   `d = R_fm` (input term: native pipeline versus analytic render), `t` the centre
   `s*` (window/deformation term). Words such as "material" mean ≥ 0.05 px in the
   README only; this is not a gate.
6. **Fit.** Not run. Native requires more than 18 observations; one patch gives 5
   frame observations (and the CUDA patch is excluded as non-converged). If the
   results show that the single patch cannot cover the lattice, the output is
   UNRUN with the missing capture list in `future_native_capture_manifest.json`.
   No Python polynomial fit is presented as the #276-validated path.

## Controls and expected outcomes (frozen)

Labels: **PASS** criterion met; **FAIL** criterion not met (retained, never
re-gated); **UNRUN** not executed; measured quantities carry no label.

| ID | Control | Expected |
|---|---|---|
| G-W | captured patch weight equals the formula, max abs ≤ 1e-6 | PASS |
| G-R | independent render, generator functions, stored frames/target/field agree (limits in step 2) | PASS |
| G-M | continuous map equals `irfft2` at every lattice point (≤1e-9 of peak) | PASS |
| G-N | parabola rule on each captured float32 map reproduces the captured candidate, max ≤ 1e-6 px (all captured iterations, both backends) | PASS |
| G-X | CUDA attempts `c2` and `c3` inputs/maps/candidates byte-identical (hash) | PASS |
| G-E | geometry: reconstructed chain reproduces the captured patch input, `rel_ac ≤ 1e-3` for all five frames of both backends | PASS |
| N-E1..N-E7 | each mutant must exceed `rel_ac 1e-3` on at least one frame (ordinary rejection by the same gate) **and** the smallest mutant `rel_ac` must be ≥ 10× the baseline maximum | all rejected |
| G-CS | image-domain sign/frame check, frames 2–4: residual `‖shift(J_f,+field_c)-T‖₂` over the window ≤ 0.5× that of each of sign-flipped, axis-swapped, zero shift | PASS |
| PC | periodic-window control (below): continuous maximum within 1e-6 px of the injected offset; integer offsets' parabola within 1e-6 px | PASS |
| N-C1..N-C4 | mutated expectations rejected by the PC criterion on at least one nonzero offset | all rejected |
| WC | window-crop control: analytic crop of `S(u+μ)` against `S(u)`; zero offset estimate exactly 0 (≤1e-9); other offsets **reported** (finite-window bias, no gate) | zero: PASS; others measured |

Stage-E mutants: N-E1 global shift sign flipped; N-E2 global shift components
swapped (x↔y); N-E3 crop X offset +1; N-E4 crop Y offset +1; N-E5 the (1,2) window
`X[42,84) Y[0,32)`; N-E6 role-swapped crop `J[0:42, 32:64]` transposed; N-E7 no
global pre-shift.

Periodic control PC and its mutants: template `T_w` = analytic target window;
frame spectrum `T_w·exp(+2πi(kx·μx/42+ky·μy/32))` (content moved by `-μ`, so the
corrective state is `+μ`). Offsets: zero `(0,0)`; integer `(1,0)`, `(0,-2)`, `(-3,2)`;
fractional `(0.25,0)`, `(0,-0.5)`, `(0.375,-0.625)`, `(-1.3,0.7)`. Mutants: N-C1
expected `-μ`; N-C2 expected `(μy,μx)`; N-C3 expected `μ+(1,0)`; N-C4 frame rendered
with the opposite sign.

If any "PASS" control fails, or a mutant is not rejected, the outcome is recorded
as FAIL, the dependent results are marked "not credited", and a distinct frozen
iteration (protocol v2) is created; the failing attempt is not edited or retried
in place.

## Resources, attempts, retention

Mac, one process, `OMP/OPENBLAS/VECLIB/MKL_NUM_THREADS=1`, `python3 -B`, NumPy only;
inputs read in place from `/tmp/mc-residual-review.h52lh3/raw` and `.../receipts`
(read-only, hash-verified); fresh scratch `/tmp/motioncorr-affine-patch-oracle-*`,
cap 512 MiB; occupancy checked beforehand. No SSH, build, native or GPU work, no
push, PR, GitHub or Notion write, no nested agent, no process signals. Each
attempt keeps its script copy, argv, log, exit code and output as
`attemptNN-*`; failures are retained and a new attempt number is used.

## Limits fixed in advance

One affine fixture (128×96×5, one realisation), one patch of nine, two backends
sharing one global trajectory each, no noise: nothing here supports a claim about
other patches, noise, other fixtures or other backends. Double-precision replays
are references, not native alternates. The production weight, estimator,
iteration/stopping rule, defaults and gates remain HELD (#279/#280/M4/M5);
this protocol proposes none of them. No native, scientific or performance
qualification.
