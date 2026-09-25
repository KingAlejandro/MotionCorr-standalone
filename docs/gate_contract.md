# MotionCorr gate contract

What each MotionCorr numerical gate measures, what it does **not** measure, and exactly how
`tools/compare_motioncorr.py` decides PASS or FAIL. Design record:
[`agents/designs/issue_58_gate_contract.md`](../agents/designs/issue_58_gate_contract.md).
Resolves [#58](https://github.com/KingAlejandro/MotionCorr-standalone/issues/58).

> [!IMPORTANT]
> **No numerical acceptance threshold changes in this document.** The `0.001` relative image
> limit stays exactly where it is and keeps failing the recorded CUDA results 0/24. It is a
> **strict CPU-agreement diagnostic**, not a statement about scientific validity. Any change to
> an acceptance limit requires a separately reviewed proposal backed by the calibration work in
> [#60](https://github.com/KingAlejandro/MotionCorr-standalone/issues/60) and the scientific
> evidence in [#61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61).

---

## 1. Four separate questions

The repository previously described two "gates". They answer only the first two of four distinct
questions, and the second was named in a way that implied the fourth.

| Tier | Question it answers | Oracle | How it runs | Enforced today | Owner |
|:--|:--|:--|:--|:--|:--|
| **A. CPU regression** | Does this build reproduce the recorded standalone CPU output byte for byte? | Committed standalone CPU output, same platform | `--gate exact` | **Yes** | #4 / #58 |
| **B. Backend CPU agreement** | How far does a new backend sit from the CPU reference, in pixel units? | Fixed standalone CPU `--j 1` output | `--gate relaxed` | **Yes**, as a diagnostic | #36 / #58 |
| **C. Motion truth** | Is known injected motion recovered, globally and in the local field? | Synthetic ground truth | reported, never thresholded | **No** | #59 |
| **D. Scientific outcome** | Is recoverable cryo-EM signal preserved? | Downstream CTF / FSC / relative B-factor | not implemented | **No** | #61 |

Three consequences, which must accompany any reported result:

- **Tier B is not Tier D.** Passing B does not establish scientific equivalence; failing B does not
  establish signal loss. B measures distance from one particular CPU implementation on one dataset.
- **Tier B is uncalibrated.** Its limits were never tied to a known amount of lost motion-correction
  signal. Until #60 reports, treat B as a *change detector*, not an acceptance criterion.
- **Upstream parity is a separate axis.** Standalone vs RELION 5.1 (#20) and standalone vs the fixed
  standalone CPU reference (#23, #25) are different comparisons that reuse the same profiles. Never
  merge them into one number. See [`spa_24_movies_validation.md`](spa_24_movies_validation.md).

---

## 2. Metrics exactly as implemented

All from `tools/compare_motioncorr.py`. One invocation compares **one movie**.

### 2.1 Corrected image

Over all `N = nx · ny · nz` pixels of the reference micrograph (`nz = 1`), in float64, with pixel
values in the MRC file's own intensity units:

| Symbol | Definition | Code | Units |
|:--|:--|:--|:--|
| `Δᵢ` | `testᵢ − refᵢ` | `:260` | intensity |
| `rmse` | `sqrt( (1/N) Σ Δᵢ² )` | `:262` | intensity |
| `max_abs_pixel_error` | `maxᵢ \|Δᵢ\|` | `:261` | intensity |
| `σ_ref` | `np.std(ref)` — population standard deviation, `ddof = 0` | `:263` | intensity |
| `relative_rmse` | `rmse / max(σ_ref, 1e-12)` | `:264` | dimensionless |

**The denominator is the reference image's population standard deviation.** It is not the test
image, not the L2 norm `‖ref‖₂`, not the MRC header `rms` word, and not a per-pixel ratio. The
reported JSON now names it explicitly as `relative_rmse_denominator` with its value in
`relative_rmse_denominator_value`.

Therefore `relative_rmse ≤ 0.001` is exactly `rmse ≤ 0.001 · σ_ref`: an absolute limit in intensity
units that **moves with the dataset**.

**Constant reference** (`σ_ref = 0`): the denominator floors at `1e-12`, so any nonzero `rmse`
produces roughly `1e12 · rmse` and fails; an exactly zero `rmse` gives `0` and passes. This is
fail-closed. Before `6c8a105` this branch returned `0.0` and passed unconditionally.

### 2.2 Global trajectory

Over the `F` frames of the `data_global_shift` block, in the units of `_rlnMicrographShiftX/Y`
(pixels):

| Symbol | Definition | Code |
|:--|:--|:--|
| `coord_rms_error` | `sqrt( (1/F) Σ_f (Δx_f² + Δy_f²) )` — RMS of the 2-D error vector | `:224` |
| `max_shift_error` | `max_f max( \|Δx_f\|, \|Δy_f\| )` — per-axis maximum | `:223` |

### 2.3 Aggregation

There is no dataset-level statistic inside the comparator. Dataset verdicts are **conjunctive over
movies** in the wrappers: `tools/compare_cuda_dataset.py` exits nonzero if any expected movie fails
or is missing, and `tools/run_all_24_tutorial_benchmark.py` raises if any per-movie report has
incomplete coverage.

---

## 3. What each profile enforces

| Check | `--gate exact` | `--gate relaxed` | `--gate custom` |
|:--|:--|:--|:--|
| Pixel payload byte-identical | **enforced** | — | — |
| Core MRC header bytes 0–223 identical | **enforced** | — | — |
| MRC labels 224–1023, run timestamp masked | **enforced** | — | — |
| Image absolute `rmse` | reported only | `≤ 0.020` | `≤ 0.010` |
| Image `relative_rmse` | reported only | `≤ 0.001` | `≤ 0.001` |
| Image `max_abs_pixel_error` | reported only | `≤ 5.0` | `≤ 5.0` |
| `coord_rms_error` | `≤ 1e-4` | `≤ 0.02` | `≤ 0.02` |
| `max_shift_error` | `≤ 1e-4` | `≤ 0.05` | `≤ 0.05` |
| STAR float tolerance | `1e-4` | `1e-3` | `1e-3` |
| STAR derived motion fields compared | yes | **excluded** | **excluded** |
| STAR difference count | `= 0` | `= 0` | `= 0` |
| Process exit status `= 0` | only with `--test-log` | only with `--test-log` | only with `--test-log` |
| Ground-truth recovery magnitude | reported only | reported only | reported only |

Points that are easy to get wrong:

- **`--gate exact` does not evaluate any RMSE threshold.** `tol_image_rmse = 1e-7` and
  `tol_image_max_err = 1e-7` are assigned at `:477` and printed as "threshold" in the human report,
  but the exact branch at `:644` compares only byte identity and header bytes. Byte identity is
  strictly stronger for every finite value, with one edge: `+0.0` vs `−0.0` gives `rmse = 0` yet
  fails byte identity. Exact is stricter than its published row, never weaker.
- **`--gate custom` is `relaxed` with a stricter default absolute image RMSE (`0.010`).** It is not a
  separate policy; it exists so that `--image-*` and `--shift-*` overrides start from a tighter base.
- **`--image-relative-rmse` defaults to `1e-3` in every profile** (`:502`) but is only *evaluated*
  outside `exact`.
- **Relaxed and custom exclude the derived motion fields** `_rlnMicrographShiftX/Y`,
  `_rlnMotionModelCoeff`, `_rlnAccumMotionTotal`, `_rlnAccumMotionEarly`, `_rlnAccumMotionLate`
  (`:313`). Global shifts are still recovered from `data_global_shift` and checked as a trajectory.
  **Local motion model coefficients are checked by nothing in relaxed mode.** That gap is #59.

### Failure behaviour

The tool exits `1` when any of these hold, and `0` otherwise:

- any enforced metric above exceeds its tolerance;
- a STAR or MRC file named on the command line is missing, or one side of a resolved pair is absent;
- an MRC cannot be parsed, dimensions or mode differ, or either image contains a non-finite pixel;
- the reference and test STAR files do not have the same frame set, or a trajectory has duplicate,
  sub-1 or non-finite frames;
- STAR metadata differs after path normalisation;
- **any unresolved or ambiguous input is reported** — for example two corrected MRCs in one
  directory (`:570`). *This is new; see §5.*
- `--ground-truth` is given but cannot be evaluated;
- `--test-log` is given and lacks a parseable elapsed time, max RSS or exit status, or reports a
  nonzero exit status;
- `--require-complete-coverage` is given and either the image or the trajectory/STAR comparison did
  not run (`:732`). *This flag is new; see §5.*
- no comparison ran at all (`:720`).

The tool exits `0`, with `coverage.complete = false`, when only part of the output was supplied and
`--require-complete-coverage` was not passed. A partial PASS applies only to the pair given.
**Ground-truth recovery is never thresholded** in any profile: `--ground-truth` prints recovery
error and fails only if it cannot be computed. Enforcing it is #59.

---

## 4. Correcting the relative-RMSE documentation

### 4.1 What was wrong

`docs/reference_gates.md` justified the absolute limit `Image RMSE ≤ 0.020` with the phrase
*"Relative RMSE < 0.1% of micrograph standard deviation"*. Those two statements are equal only when
`σ_ref = 20.0` exactly, because `0.020 = 0.001 · σ_ref ⟺ σ_ref = 20`. No dataset in this repository
has `σ_ref = 20`. The phrase also survived unchanged when the limit was doubled from `0.010` to
`0.020` in `93556b4`, so it was never recalculated.

The #4 design spec (`agents/designs/issue_4_define_the_reference_outputs_and_numeric.md` §3.3)
specified a different metric again — relative L2 error `‖Δ‖₂ / ‖ref‖₂`. The code implements
`rmse / σ_ref`. The two agree only for a zero-mean reference.

### 4.2 The effective limit in real data

| Dataset | `σ_ref` | `rmse` limit implied by `relative_rmse ≤ 0.001` | Absolute limit `0.020` | Which one binds |
|:--|--:|--:|--:|:--|
| 24 SPA tutorial micrographs | 0.806 – 0.935 (median 0.886) | 0.000806 – 0.000935 | 0.020 | **relative**, 21.4x – 24.8x stricter |
| Committed 128×128 synthetic fixture | 64.281 | 0.0643 | 0.020 | **absolute**, 3.2x stricter |

On the tutorial data the absolute limit is **~22x looser** than the relative one and never binds; on
the committed fixture the ordering reverses. An absolute pixel-RMSE limit is not portable across
datasets, which is why the two checks cannot be described as equivalent.

For the same fixture, the #4 spec's relative-L2 denominator is `‖ref‖₂/√N = 837.44` against
`σ_ref = 64.28` — a factor of **13.03**, because the reference mean is 834.97, not 0.

---

## 5. Numerical policy history

| Commit / PR | Change | Effect |
|:--|:--|:--|
| `59e2dd6` (PR #19) | Gates introduced. Relaxed: `rmse ≤ 0.010`, `max ≤ 0.5`. `relative_rmse` computed but **not gated**. Denominator was the MRC header `rms` word, falling back to `np.std`. | Baseline |
| `93556b4` | Relaxed `rmse` `0.010 → 0.020`, `max` `0.5 → 3.0`. Image failed only if `rmse > tol` **and** `relative_rmse > 1e-3`. | **OR policy**: either metric passing was sufficient |
| `a5886a3` | Relaxed `max` `3.0 → 5.0`. Fail-closed fixes for inputs, frame sets, STAR status, exact-gate headers, exit status. | Tightening |
| `6c8a105` | Split the image check into two **independent** requirements. Denominator changed from the header `rms` word to computed `np.std(ref)`. Constant-reference behaviour changed from returning `0.0` (fail-open) to `rmse / 1e-12` (fail-closed). Added `--image-relative-rmse`. | **AND policy**: both metrics must pass. This is a numerical-policy change and was not previously recorded. |
| this change (#58) | Unresolved or ambiguous inputs now fail the gate. Added opt-in `--require-complete-coverage`, used by `tools/run_regression_tests.sh`. Report names the relative-RMSE denominator and its effective absolute limit. | Fail-closed; **no acceptance threshold changed** |

The OR-to-AND transition is what makes the tutorial CUDA results fail. Under the `93556b4` policy
all 24 movies would have passed the image check, because their absolute RMSE (0.00266–0.00908) is
inside `0.020`. Under the current policy they fail on `relative_rmse` alone.

### Two fail-open paths closed here

**F1 — unresolved or ambiguous inputs did not fail.** Discovery errors were rendered in the report
but never set the exit status. When the problem is **symmetric** — two corrected MRCs in the
reference directory *and* two in the test directory — both sides resolve to nothing, the image
comparison is skipped, and the tool printed two "Multiple corrected MRCs" errors alongside
`overall_status: PASS` and exit `0`. This contradicted §6 of `reference_gates.md` and the stated
intent of `6c8a105`. An asymmetric ambiguity was already caught by the missing-pair check.

**F2 — complete coverage could not be required.** `coverage.complete` was computed and printed, but
no caller could ask the comparator to enforce it: two directories that each hold a STAR and no
corrected MRC exit `0` with `coverage.complete = false`. The three Python wrappers each
re-implement the check; `tools/run_regression_tests.sh`, the Tier A entry point, did not check it
at all. This was not a reachable false pass for Tier A today — the committed reference bundle always
supplies one MRC, so a missing or ambiguous *test* MRC is caught by the pair-resolution check. The
flag makes the requirement explicit and keeps it true if the reference bundle, the output naming or
the discovery filter changes. It is **off by default**, so no existing caller changes behaviour.

---

## 6. Reproducible commands

All commands run from the repository root with a Python 3 that has NumPy.

**Tier A — CPU regression on the committed fixture** (requires a built `./build/motioncorr`):

```bash
./tools/run_regression_tests.sh ./build/motioncorr
```

or directly:

```bash
python3 tools/compare_motioncorr.py \
  --ref  test-data/fixtures/reference_output \
  --test <run_output_dir> \
  --gate exact \
  --require-complete-coverage
```

Verified on this branch with a fresh Release build (macOS arm64, AppleClang, FFTW 3.3.10,
`cmake -DCMAKE_BUILD_TYPE=Release`): exact gate **PASS**, pixel-identical, 0 STAR differences,
0 header difference bytes, complete coverage. The same run reports ground-truth recovery of
`0.071437 px` RMS and `0.100020 px` maximum — printed, **not gated**, which is gap #1 in §8.

**Tier B — backend agreement against the fixed CPU `--j 1` reference**, one movie at a time:

```bash
python3 tools/compare_motioncorr.py \
  --ref-mrc  cpu_j1/Movies/<movie>.mrc   --test-mrc  cuda/Movies/<movie>.mrc \
  --ref-star cpu_j1/Movies/<movie>.star  --test-star cuda/Movies/<movie>.star \
  --test-log cuda/time_v.log \
  --gate relaxed --require-complete-coverage \
  --json-out reports/<movie>.json
```

**Reproduce the effective-limit table in §4.2** from committed artefacts, no GPU and no movies:

```bash
python3 - <<'EOF'
import json, statistics
movies = json.load(open("docs/cuda_24_movies_gate2_rerun.json"))["movies"]
std = [m["image_rmse"] / m["relative_rmse"] for m in movies]          # sigma_ref = rmse / rel_rmse
print("sigma_ref      min %.6f  median %.6f  max %.6f" % (min(std), statistics.median(std), max(std)))
print("0.001*sigma    min %.6f  median %.6f  max %.6f" % (0.001*min(std), 0.001*statistics.median(std), 0.001*max(std)))
print("0.020 / (0.001*sigma)  min %.2fx  median %.2fx  max %.2fx"
      % (0.020/(0.001*max(std)), 0.020/(0.001*statistics.median(std)), 0.020/(0.001*min(std))))
EOF
```

```text
sigma_ref      min 0.806115  median 0.885955  max 0.935243
0.001*sigma    min 0.000806  median 0.000886  max 0.000935
0.020 / (0.001*sigma)  min 21.38x  median 22.57x  max 24.81x
```

**Reproduce the fixture scale in §4.2:**

```bash
python3 -c "
import sys; sys.path.insert(0, 'tools')
import numpy as np
from pathlib import Path
from compare_motioncorr import parse_mrc
_, pixels, _ = parse_mrc(Path('test-data/fixtures/reference_output/synthetic_128x128_8frames.mrc'))
x = pixels.astype(np.float64)
print('mean %.6f  sigma %.6f  L2/sqrt(N) %.6f  ratio %.4f'
      % (x.mean(), x.std(), np.sqrt((x**2).mean()), np.sqrt((x**2).mean())/x.std()))
"
```

```text
mean 834.965232  sigma 64.281425  L2/sqrt(N) 837.435992  ratio 13.0277
```

**Contract regression tests** (pin the denominator, constant-reference behaviour, exact-gate scope,
fail-closed inputs, and the coverage flag):

```bash
cd tools && python3 -m unittest test_compare_motioncorr -v
```

---

## 7. Current recorded results — unchanged

| Comparison | Profile | Result | Evidence |
|:--|:--|:--|:--|
| Standalone `j=1` vs PR #25 fixed CPU reference, 24 movies | exact | **24/24 PASS** | [`spa_24_movies_validation.md`](spa_24_movies_validation.md) |
| Standalone `j=4` vs standalone `j=1`, 24 movies | exact | **24/24 PASS** | same |
| Standalone `j=1` vs RELION 5.1 `j=1`, 24 movies | exact | **1/24 PASS** — open as #20 | same |
| CUDA vs fixed CPU `j=1`, 24 movies | relaxed | **0/24 PASS**, `relative_rmse` 0.002899–0.010082 vs `0.001`; every other check passes | [`cuda_global_alignment_validation.md`](cuda_global_alignment_validation.md), [`cuda_24_movies_gate2_rerun.json`](cuda_24_movies_gate2_rerun.json) |
| Small synthetic CUDA fixture | relaxed | PASS | [`synthetic_cuda_regression.md`](synthetic_cuda_regression.md) |

The CUDA row is a **Tier B** result. It bounds CPU disagreement at ≤ 1.01% of the reference
micrograph standard deviation and ≤ 3.32 intensity units in the worst pixel. It does not measure
recoverable signal. Root cause is #36.

---

## 8. Known gaps

| Gap | Consequence | Owner |
|:--|:--|:--|
| Ground-truth recovery is reported but never thresholded | A backend can drift arbitrarily from known injected motion and still pass | #59 |
| Local motion model coefficients are compared by nothing in relaxed mode | A local-field defect is invisible to Tier B unless it moves enough pixels | #59 |
| Tier B limits are uncalibrated against any known signal loss | Cannot say what a given failure costs scientifically | #60 |
| No Tier D metric exists | "Scientific equivalence" cannot currently be claimed or refuted by any gate | #61 |
| `tools/test_compare_motioncorr.py` is not registered with CTest | The contract tests are not run by CI; CI's Python has no NumPy | #5 |
| Exit status is only checked when `--test-log` is supplied | A comparison without a log cannot observe process failure | #58, documented above |
