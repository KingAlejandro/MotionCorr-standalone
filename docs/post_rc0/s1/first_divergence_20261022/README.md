# W4 first-divergence diagnosis, 2026-10-22

Diagnostic branch `diag/known-motion-first-divergence-20261022`, based on #273
`805d9de27898b4a10e6212e65098d5995a40fdb1` (numerical/native source
`d751ff28594902eca75d665ff116e662653481aa`). Evidence and test overlays only:
production sources, defaults, gates, iteration and publication policy are
unchanged. Historical #273 totals stay **2 PASS / 10 FAIL / 4 UNIDENTIFIABLE**;
nothing here relabels an outcome. A causal explanation is not an accuracy PASS.

## Result

Revised after independent review round 1 (`review/round1-response.md`).

For the simple high-signal global-only cases (integer, fractional; 128×96×5,
model 0, 1×1 patch), the inputs, truth convention, forward FFT, reconstruction
path and STAR serialization are correct within float precision, and the
captured weights match the inherited weight formula (a fidelity check, not a
check that the weight is physically right).

Taking the inherited objective as given, the earliest stage that departs from
the maximum of the objective it estimates is the **sub-pixel peak estimate**.
The source specifies this step as quadratic interpolation ("Quadratic
interpolation by Jasenko"): separable 3-point fits through the integer winner.
That fit is biased when the weighted CCF peak has a nonzero cross term
(principal axes rotated relative to the pixel axes); axis-aligned anisotropy
alone would give no bias. On the 5-frame fixtures, the sum-of-others iteration
driven by this biased estimate does not converge, and the 0.5 px update
tolerance or the 5-iteration limit ends it 0.3–0.6 px from truth.

There is no single exclusive cause. The inherited weight shape (x frequency
normalized by `nx/2+1`, y by `ny`) creates much of the cross term, and an
independent reviewer replay with an isotropic diagnostic weight and the
unchanged parabola passes both 5-frame fixtures (0.043 / 0.049 px). Weight shape
and estimator are co-causes on these fixtures; either change alone suffices
offline. The isotropic weight is not a safe change either: a reviewer probe
with 20 synthetic frames diverges to 11.8 px with it (0.28 px with the
production weight). Nonconvergence is shown for 5 frames only; reviewer probes
at 9, 13 and 20 frames converge slowly and reach truth by 50 iterations, so at
other frame counts the stopping rule can be a co-cause.

Float32 quantization of the pedestal-dominated CCF map is a further error
source (peak curvature is only 4–7 ULPs), but it is not needed for the simple
failures: the same algorithm in double precision also fails. For the
`pedestal` case quantization is inferred to be sufficient on its own: offline
float32 rounding of the exact first-iteration map gives a single value across
the search window, consistent with the native all-zero trajectories and RMSD 0
logs. No native pedestal map was captured.

## Native stage injections (12 processes, frozen manifest)

`campaign-manifest.json` (committed in `daaa2217` before launch) froze 12 of the
24 allowed MotionCorr processes and each expected result. All 12 ran once,
sequentially, exit 0; nothing was retried. Expectation outcomes below are
diagnostic statements about this campaign. The checker, ROI and gates are the
unchanged #267/#273 ones.

| Arms (CPU / CUDA) | Stage tested | Result |
|---|---|---|
| `neutral-*-integer` | overlay inert when disabled | full-precision trajectory equals #275 capture-off exactly; STAR equal; MRC equal except the Relion timestamp label; checker FAIL as historically (0.298 / 0.285 px). **Expectations met** |
| `truth-*-integer`, `truth-*-fractional` | known-correct trajectory → actual reconstruction and STAR | runtime model equals truth exactly; STAR equals runtime (0 px); checker PASS **by construction**; published sum contrast-normalized RMSE 1.07e-5 / 1.09e-5 (integer), 7.1e-6 / 6.7e-6 (fractional; the checker's bilinear truth oracle is 0.0237). **Met** |
| `perturbed-*-integer` | negative control (frame 4 x + 1 px) | runtime equals the perturbed file; checker FAIL (0.447 px); published-sum error 0.0648, ~6000× the truth arm. **Met** |
| `fixedref-*-integer` | actual float CCF/peak path with unshifted frame 0 as a fixed known template | iteration 1 recovers truth exactly on both backends, iteration 2 RMSD 0; field 0 px; checker PASS. **Met** |
| `fixedref-*-fractional` | same, fractional | checker FAIL as predicted: 0.308 px CPU (**met**), 0.495 px CUDA (**NOT MET**) |

Two magnitude bands exist and both are recorded. The frozen manifest
(`daaa2217`) states "roughly 0.26–0.34 px"; the evaluator test of 0.2–0.45 px
was added in `analyze_native.py` (`98855b28`, committer time 19:16:41 UTC, before
the 19:20:31 UTC launch but not part of the frozen manifest). CPU 0.308 px is
inside both; CUDA 0.495 px is outside both.

The NOT MET arm is retained as is. Its frame-4 iteration-1 candidate is
(−3.833, 2.833) against CPU (−3.167, 2.000) and truth (−3.25, 2.125): about one
integer winner per axis, with small-integer-ratio vertices typical of the
quantized maps. A near-tie flip is the likely cause but is inferred; no map was
captured for that arm. It does not contradict the attribution: the arm fails, as
the parabola-bias explanation requires.

Together with the offline evidence below, this localizes the simple failures:
the actual reconstruction, STAR serialization, forward transform and float CCF
path recover integer motion exactly once the reference is a single template, so
under the inherited weight the integer failure needs the sum-of-others blending
plus the biased parabola; the fractional failure persists even with an ideal
template because of the parabola bias under that weight.

Native source: git archive of 805d9de2, SHA-256 `1df40992…` (identical to the
#275 archive), plus `make_overlay.py`/`w4_inject.h` changing only
`src/motioncorr_runner.cpp`, `src/acc/cuda/cuda_alignpatch.cu` and adding
`src/w4_inject.h` (before/after hashes and full diff in the receipts). CPU
binary `8d868ddc2a8b81e3c3c5dc3982dee029031bbe7e9ed4801c9aaf540ce2174ad0`,
CUDA `fb509ef3458855df1d2038adf63b903635d61617a2be47e5dba1afb319aa7e29`.
These are test builds; no native result here is credited to any other source.

## Stage evidence (offline, retained arrays; no MotionCorr execution)

Inputs are the original NumPy 2.5.3 fixtures (MANIFEST
`9697c203…`) and the #275 capture arrays, all bound by SHA-256 through the
committed #275 receipt index (`6ae48678`) → `file-index.json`
(`31255dab…`). The six other fixtures were regenerated locally and are
hash-identical to the pinned MANIFEST. Mac Python 3.13.7, NumPy 2.4.2,
SciPy, one numeric thread.

| Stage | Check | Result |
|---|---|---|
| Generator/input | stored float32 frames vs independent double re-render | max 3.8e-6 (half a float ULP at 100); frame 0 = target bitwise; integer frames equal circular shifts of the target within one float ULP |
| Truth convention / information | double fixed-template CCF of each stored frame against the target, production weight, exact continuous maximum | integer 7e-9 px, fractional 2.5e-7 px RMS from the fixture field |
| Forward FFT | captured iteration-1 spectra vs double `rfft2/N` | max abs 2.0e-6 (integer), 5.1e-6 (fractional); DC 100.0046 |
| Weights | captured float weights vs double evaluation of the inherited formula | ≤ 6e-8 (fidelity to the inherited formula only) |
| CCF map (all 100 captured records) | peak second differences; float inverse error | curvature 4–7 ULPs at the ~40004 pedestal; window range ≤ 517 ULPs; inverse error ≤ 2.5 ULPs; every finite difference is an integer number of ULPs, so each native vertex offset is a ratio of small integers and the trajectory is rational (e.g. −0.7, −12/7) |
| Same-state iteration 1 | native candidate vs the same parabola rule on the double-precision map of the same state | up to 1.22 px (frame 1, both backends; vs the continuous maximum: 0.58 px) |
| Estimator oracle | 81 known offsets in [−1,1]², actual target, production-weighted objective, double | parabola max 0.544 px, RMS 0.313 px; integer offsets exact; exact maximum ≤ 5.7e-7 px |
| Peak geometry | Hessian at the exact peak | Hxy/Hxx 0.68, Hxy/Hyy 0.85, curvature ratio 7.3; the cross-term formula reproduces the parabola output within 0.0026 px, so each 1D slice fit is near exact and the error comes from slicing through the integer winner |

Offline replays from the identical captured iteration-1 spectra. Only the first
row is the specified algorithm; each other row changes one component (field
RMS in px vs truth; gate is 0.226 px):

| Arm | integer CPU / CUDA | fractional CPU / CUDA |
|---|---|---|
| native (retained #273/#275) | 0.298 / 0.285 | 0.592 / 0.379 |
| specified algorithm, double | 0.587 / 0.493 (a range: inputs differ by ≤ 2e-6) | 0.369 / 0.369 |
| float32-rounded map | 0.360 / 0.360 | 0.466 / 0.466 |
| double, tolerance 1e-9, 50 iterations | 0.897 / 0.303 (not converged) | 0.390 / 0.391 (not converged) |
| double, exact continuous maximum | 0.090 / 0.090 | 0.038 / 0.038 |
| …and tolerance 1e-9, 50 iterations | 0.000 / 0.000 | 0.000 / 0.000 |
| fixed frame-0 reference, double | 0.000 / 0.000 | 0.260 / 0.260 |
| fixed frame-0 reference, float32 map | 0.000 / 0.000 | 0.335 / 0.335 |
| fixed frame-0 reference, exact maximum | 0.000 / 0.000 | 0.000 / 0.000 |

Interpretation:

- Truth is a fixed point of the sum-of-others objective: with the exact maximum
  the iteration converges to it exactly. With the parabola and 5 frames it does
  not converge even after 50 iterations, so for these fixtures the stopping rule
  only decides where the non-converging trajectory is cut. This is specific to
  N = 5: the reviewer's linearization gives an unstable eigenvalue −1.196 at
  N = 5 but −0.98 to −0.85 at N = 9–20, and synthetic 9/13/20-frame probes reach
  truth by 50 iterations while still failing at 5 iterations / 0.5 px. There
  the stopping rule is a co-cause.
- With one known template the parabola is exact for integer offsets, so integer
  motion is recovered once the blended reference is removed. The blended
  sum-of-others reference makes iteration-1 offsets fractional even for integer
  motion, which exposes the bias.
- CPU and CUDA double replays diverge (0.587 vs 0.493) from inputs that differ by
  ≤ 2e-6: the estimator is ill-conditioned near the frequent exact ties
  (16/25 and 14/25 integer records have tied maxima).
- The inherited weight normalizes x frequency by `nfx = nx/2+1` and y by `ny`,
  so x is damped ~3.9× harder than y; dose weighting in the same file normalizes
  x by `nx²`, so the code is internally inconsistent. With an isotropic
  diagnostic weight the parabola error falls from 0.544 to 0.169 px max
  (Hxy/Hxx 0.68 → 0.16); without weighting, 0.091 px. The reviewer's isotropic
  5-iteration replays pass both fixtures (0.043 / 0.049 px), so the weight shape
  matters as much as the estimator here. The same weight change fails a 20-frame
  fractional probe (11.8 px vs 0.28 px with the production weight), so this is
  diagnostic only. The weight is inherited from the RELION 5.1 extraction
  (`4499be23`).

## 16-arm attribution ledger

Historical statuses are unchanged; `ledger.json` holds the per-arm numbers,
evidence and next step. CPU and CUDA share an attribution unless noted.

| Case | #273 CPU / CUDA (field RMS px) | Attribution | Earliest divergence located | Remaining uncertainty → next step |
|---|---|---|---|---|
| zero | PASS / PASS (0 / 0) | control | none | none |
| integer | FAIL / FAIL (0.298 / 0.285) | co-causes: inherited weight shape and separable parabola, with nonconvergence at N = 5; quantization contributes | relative to the inherited objective: global iteration 1 sub-pixel peak estimate (natively and offline) | quantization share not bounded natively → two held questions (weight; estimator/iteration/stopping) |
| fractional | FAIL / FAIL (0.592 / 0.379) | same co-causes; bias persists with an ideal template under the inherited weight | relative to the inherited objective: sub-pixel peak estimate | CUDA fixed-template tie flip inferred → optional map capture |
| affine | FAIL / FAIL (0.455 / 0.323) | global: same mechanism (descriptive); local: unresolved | not localized | patch-level known-template oracle on #275 (2,1), then #276-validated fit |
| pedestal | FAIL / FAIL (2.395 / 2.395) | inferred: float32 CCF map resolution under the 4096 pedestal (#262 domain) | inferred CCF map, iteration 1: offline float32 rounding gives one value across the window; native global and all 9 patches return zero motion | offline + native logs only, no native map → W2 DC arms; optional native map capture |
| noisy | FAIL / FAIL, OUTSIDE_FIXED_ROI (2.647 / 2.978) | unresolved; global appears noise-limited | not localized | repeated-seed known-template study (#238 plan C) |
| flat | UNIDENTIFIABLE / UNIDENTIFIABLE, VALID (2.378 / 2.378) | intrinsic: no signal | none in arithmetic (exact map constant) | no quality state is emitted → M4 |
| repeated | UNIDENTIFIABLE / UNIDENTIFIABLE, OUTSIDE_FIXED_ROI (18.68 / 68.67) | intrinsic periodic ambiguity with float ties | CCF maximum selection among 475–1710 tied maxima picks large aliases | alias choice is tie-order dependent → M4 |

#264 (guard domain) cannot confound the integer, fractional, flat and repeated
arms: they use model 0 with a 1×1 patch, so no guard or polynomial runs. #265
(model-coefficient truncation) does not apply to them; their global STAR rows
equal the runtime trajectory within 4.8e-6 px, and exactly for the injected
values. Pedestal is different: it ran model 1 with 9 patches. All 9 patches
logged RMSD 0, the fit RMSD is 0 and all 36 STAR coefficients print as zero. A
zero polynomial cannot exceed the guard on either domain, so #264 is unlikely to
change the pedestal outcome, but the guard decision is not logged and the runtime
coefficients were not captured: this is an inference, and #264/#265 are not
excluded for pedestal by proof. #266 (CPU non-Hermitian c2r input) is not needed
to explain the simple failures: the CUDA path, which projects explicitly (#254),
and the offline double replays fail the same way. All three remain untested for
affine and noisy.

## Proposed separate items (not implemented or filed here)

Two separate, cross-linked HELD/file-only questions. Both behaviours are
RELION-inherited, so under current policy any parity-breaking change needs
maintainer sign-off. No fix, default or adoption is recommended.

1. **Alignment weight x-normalization.** The global and patch B-factor weight
   normalizes x frequency by `nx/2+1` and y by `ny`, inconsistent with dose
   weighting's `nx²`. Evidence: `estimator/attempt02.json`; reviewer isotropic
   replays (`review/round1/indep.json`). Counter-evidence: isotropic weight fails
   a 20-frame fractional probe at 11.8 px (`review/round1/ndep.log`).
2. **Peak estimate, iteration and stopping.** Separable 3-point quadratic
   interpolation on correlated (rotated) peaks, its interaction with the
   sum-of-others gain N/(N−1), and the 5-iteration / 0.5 px stop. Evidence:
   offline replays, native fixed-template arms, reviewer linearization and the
   N = 9/13/20 probes, where longer iteration reaches truth.

W2 (#262) already covers the quantization term; the pedestal arm is its
clearest positive case.

## Files

- `offline_stages.py` (+ `offline_stages_lib.py`, verbatim copies asserted at run
  time): stage table and replays. Attempts `offline/attempt01` (exit 1, CUDA
  capture filename assumption, no output), `attempt02` (exit 0), `attempt03`
  (exit 0, adds estimator/tolerance arms) are retained with their exact scripts.
- `parabola_bias.py`: known-shift estimator oracle; `estimator/attempt01`
  (production weight) and `attempt02` (adds weight variants).
- `ledger_inputs.py`: 16-arm evidence from the committed #273 archive,
  regenerated fixtures and #275 affine/noisy global captures; `ledger/attempt01`.
- `make_overlay.py`, `w4_inject.h`: test-build overlay. `campaign-manifest.json`
  froze 12 native arms and expected results before launch (commit `daaa2217`).
- `remote_build.py`, `remote_run.py`, `analyze_native.py`: native build, campaign
  and evaluation (`native/evaluation-attempt01.json`).
- `native/receipts.tar.gz` (264 files, SHA-256 in `native/receipt-index.json`,
  which also binds 72 remote-only plot files): logs, argv/env/affinity, exits,
  health, locks, inputs, STAR/MRC, checker JSONs, full-precision state, overlay diff.
- `final_ledger.py` → `ledger.json` (revised after review round 1; the
  pre-review version is at `7d85898d`).
- `review/`: round-1 reviewer artifacts preserved byte-identical in `round1/`,
  bindings in `round1-artifacts.json`, responses in `round1-response.md`.

## Resources, commands and receipts

Host `4-gpu-vm` via `ssh -J ccp4-gateway 4GPUs`; fresh scratch
`/mnt/clathrin/alex-motioncorr-first-divergence-20261022-daaa2217` (272 MB);
fixtures copied read-only from the #275 scratch and hash-verified. All drivers
and children ran under `taskset -c 14,15`; compile parallelism 2; `--j 1`, numeric
threads 1. GPU1 only, UUID `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`.

- Build: the first preflight found `/tmp/motioncorr-build.lock` held by the DC
  lane; no build was launched until a later check found it free. Launch attempt 1
  (PID 3084798) never started the driver because the backgrounded command list
  raced its PID file; no build ran and no lock was taken (`launch-attempt1.json`).
  Attempt 2, PID 3087082, held the build lock exclusively 19:15:35–19:20:00 UTC,
  exit 0 (configure/build/ldd for CPU and CUDA all 0). Release, nvCOMP off, sm_80,
  CUDA 12.8.
- Campaign: PID 3095797, `remote_run.py`, exit 0. GPU1 correctness lock acquired
  nonblocking at 19:20:31 UTC and released at 19:20:39 after the final health
  sample; bench lock probed free and released. Health before, after each CUDA arm
  and final: UUID/index match, no compute app, volatile ECC 0/0, 1 MiB used.
  Driver reaped; GPU idle afterwards.
- argv per arm: `BINARY --i CASE.star --o ROOT/runs/LABEL/out --use_own --j 1
  --patch_x 1 --patch_y 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW
  --first_frame_sum 1 --last_frame_sum 5 --skip_logfile [--gpu 0]`, cwd
  `ROOT/fixtures`, plus the arm's `MC_W4_*` variables.

No timing is claimed; application stage durations in raw logs are not
performance evidence. Root checkout and other workers' scratch were not touched.

## Limits

- Simple cases are 128×96×5 noise-free fixtures with one geometry, B = 150 and
  default search; the estimator bias depends on peak shape, so magnitudes do not
  transfer to real movies without the plan-C extension.
- The nonconvergence finding is bounded to 5 frames. Reviewer probes at
  9/13/20 frames (synthetic phase-ramp frames from the target, not fixtures)
  converge slowly; there the stopping rule can be a co-cause.
- "Earliest divergence" is relative to the inherited objective, including its
  weight. The weight itself is only checked for fidelity to the inherited formula.
- Offline replays use double arithmetic on float32 captured spectra and the CPU
  row-major tie rule; they are references, not native trajectories.
- The exact-maximum and isotropic-weight arms are diagnostic counterfactuals.
  They are not a proposed estimator, weight, gate or default, and their small
  errors are not an accuracy PASS.
- Affine and noisy local stages, and the pedestal patch maps, are not localized.
- No downstream science, full suite or performance claim.
