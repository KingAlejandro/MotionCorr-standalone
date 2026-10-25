# W4 loaded-fixture amendment (v2) and all-patch inherited-objective oracle (v1)

Frozen 2026-10-25, before any output of these scripts exists. Prepared offline on the Mac; nothing
numerical was executed there (only parsing, hashing and tar packaging). Diagnostic only: no gate,
default, estimator, weight, contract or C1/main change, no verdict relabel. Historical #273 totals
(2 PASS / 10 FAIL / 4 UNIDENTIFIABLE), the five-frame failures, the N=5/9/13/20 probes and the N=20
11.833 px counterexample stay as they are. Field limits 0.20/0.40/0.80 Å (runtime and STAR separately)
are untouched; the 0.15/0.3 px and 0.6/0.9 slope numbers below are routing labels, not gates.

## 0. Retained first failure (not retried, not relaxed)

Parent run of `w4_allpatch_decomposition.py` v1 (sha256 `6e483374…f061`) on cpu64, CPU 62, Python 3.12.3,
NumPy 1.26.4, input package `1333c4b8…cf96`: exit 1, `regenerated fixtures/affine_field.npy differs from
pinned fixture`; `w4_shrinkage.py` UNRUN. Records: `/tmp/motioncorr-20261025-parent/w4-cpu64-reproduction.json`,
`w4-cpu64-RESULT.json`, `w4-cpu64-out/`. v1 and its hash gate stay unchanged; v2 is a new version.

## 1. Inputs and pins

| Input | sha256 | Origin |
|---|---|---|
| `fixtures/affine_field.npy` (983168 B) | `839c484f…5799` | parent collection, byte-exact from the old 4GPUs #275 scratch (`/tmp/motioncorr-20261025-parent/w4-original-fixtures/`) |
| `fixtures/affine_target.npy` (49280 B) | `287e0a82…da70` | same |
| `fixtures/affine.mrcs` | `1cf918d5…260a` | Mac `/tmp/mc-v2/fixtures` (Oct 21 generation dir); equals the #275 file-index pin |
| `fixtures/MANIFEST.json` | `9697c203…02dc` | same dir; equals the retained `fixture-MANIFEST.json`; records generation with NumPy **2.5.3** |
| `r275/file-index.json` + 10 `runs/{cpu,cuda}-affine-on/` files | index `31255dab…65c3`; each file checked against the index | #275 receipts `7cda1e89…e5db` (6ae48678) |
| `src805/` 4 files | `src805/BLOBS.txt` (git blob + sha256 at 805d9de2) | `git show 805d9de2:<path>` |
| `ref/attempt02.json` | `0bcf6879…bb72` | reviewed (2,1) oracle output, git blob `67c96c03` at 83db13d2 |
| `ref/shrinkage-attempt01.json`, `ref/allpatch-attempt01.json` | `0a2d16d2…4629`, `4fe5185e…18dc` | Mac v1 outputs in `/tmp/motioncorr-20261025-w4attr/out` (bound by its SHA256SUMS) |

The two NPY headers are standard format 1.0 with a 128-byte header (`'<f8'`, shape (5,96,128,2) and
`'<f4'`, shape (96,128), C order), read from the bytes.

## 2. Phase A: control D, fixture identity (`w4_fixture_diag.py`)

Measures, on the executing host and NumPy:
- **S (serialization):** `np.save(np.load(pinned))` against the pinned bytes, header and payload separately.
  This isolates the NPY header format from the arithmetic.
- **R (regeneration):** generator output at 805d9de2 against the pinned arrays, header bytes and payload
  separately: differing elements, max abs, max ULP, ULP histogram. The movie is compared with the pinned mrcs data.
- **L (localisation, report-only):** field by elementwise closed form (no matmul) and target by scalar libm
  `math.cos/exp`, each with the generator's operand order, against both pinned and regenerated arrays.

Frozen classification: `NOT_REPRODUCED` if the regenerated field hash equals the pin (contradicts §0;
stop and investigate); `HEADER_FORMAT_ONLY`; `PAYLOAD_WITHIN_LIMITS` / `HEADER_AND_PAYLOAD_WITHIN_LIMITS`
when field max abs ≤ 1e-12 px and target and movie ≤ 1e-5 (the reviewed oracle's existing G-R limits);
otherwise `*_SEMANTIC` or `UNEXPLAINED`. **`adoptable` is true only for the three non-semantic classes.**
Phase B scripts refuse to run without a completed, adoptable diagnostic and record its sha256.
Expectation (unverified): identical headers and ULP-level payload differences from NumPy's SIMD
transcendentals and/or the matmul path. That is a guess, and only the run decides it.

## 3. Phase B (only if Phase A is adoptable)

1. `w4_allpatch_decomposition_v2.py`: v1 with only the fixture block changed. It loads the pinned field,
   target and mrcs (the retained checker's own input path, `check_motion_diagnostics.py:183-185`), checks
   their pins, and also pins `file-index.json`. Diff against v1: header docstring, argv, index pin,
   diagnostic precondition, fixture block, schema name.
2. `w4_shrinkage.py` v1 unchanged (it never read fixtures).
3. `compare_json.py`: every numeric leaf of the cpu64 outputs against the Mac v1 outputs (1 and 2).
   Frozen reading: **reproduced** if max abs diff ≤ 1e-5 and no structural differences outside the ignored
   keys (`inputs`, `numpy`, `python`, `schema`). The values are rounded to 6/4 dp, so a single last-digit
   rounding flip is possible. Anything else is reported as a reproduction discrepancy. Per the parent's
   instruction, the time-convention finding stays provisional until both this and the independent Gemini
   review support it. Gemini's qualifications (coupled half-time/zero-anchor convention; 0.242/0.333 is an
   exact-observation counterfactual, not a floor; native observations still fail at integer time,
   0.358/0.288) are wording corrections; this reproduction does not test them.
4. `w4_objective_oracle.py` (below).

## 4. Oracle definitions (frozen)

Per backend b, its own `global.txt` g (frame 0 = 0), patch p of the 3×3 grid (42×32 windows
x∈{[0,42),[42,84),[84,126)}, y∈{[0,32),[32,64),[64,96)}, `motioncorr_runner.cpp:3474-3519`), frames f=1..4.
Weight, search ±15, native Fourier-shift phase convention and the Newton continuous maximum are copied
unchanged from the reviewed oracle (`affine_patch_oracle.py` `fc3f11b6…4d31`); the integer winner is
vectorised with identical first-maximum semantics.

| Symbol | Definition |
|---|---|
| K (known) | pinned `affine_field[f, Y, X] − g[f]` at the logged centre (REPORT §4 convention; equals the shrinkage script's known) |
| N (native) | STAR observation `obs[f] − obs[0]` (print precision); accepted patches only (CPU 9, CUDA 8; CUDA (2,1) not converged) |
| **R_fm** | static template: continuous max of weighted CCF(analytic target window, analytic window of frame f pre-shifted by g, no wrap); REPORT §6 reference |
| **R_loo** | actual leave-one-out objective: alignPatch iteration (reference = Σ shifted frames − frame, anchor to frame 0, accumulate, re-shift in window Fourier space) on analytic windows, continuous peaks, iterated to its fixed point (increment RMSD < 1e-9 px, ≤ 60 iterations) |
| **R_pipe_loo** | R_loo on pipeline windows: double FFT of the pinned frames, global Fourier shift by g (periodic wrap), crop |
| R_loo_iter1, R_loo_native_stop | report-only: LOO iteration 1 (state 0); LOO with the native stop rule (RMSD < 0.5 px, ≤ 5 iterations) |

Metrics per reference X over accepted patches × frames 1–4 (vector RMS): `native − X`, `X − K`,
`slope_y(X on K) = Σ X_y K_y / Σ K_y²` (x reported too), correlations; per-patch norms.

Routing per reference (REPORT §6 thresholds, unchanged): OBJECTIVE_DOMINATES if RMS(native − X) ≤ 0.15 px
and slope_y ≤ 0.6; ARITHMETIC_DOMINATES if slope_y ≥ 0.9 and RMS(native − X) ≥ 0.3 px; else MIXED. An
LOO reference with any accepted patch lacking a fixed point is UNDETERMINED_NO_FIXED_POINT. **Effective route
= the common route if R_fm, R_loo and R_pipe_loo agree, else MIXED (reference-sensitive).** The parent has
already chosen the eight reviewed CPU13 captures, so the route no longer decides whether to run them. It labels
the attribution, and it informs whether a CUDA capture protocol is worth writing (ARITHMETIC on CUDA).
No route is predicted in advance. Nothing is tuned after outcomes: any change is a new version.

## 5. Oracle controls (frozen; any FAIL marks every route "not credited")

| ID | Check | Limit | Expected |
|---|---|---|---|
| C-GEN | independent forward model vs generator functions, 1000 points | ≤ 1e-12 | PASS |
| C-WIN | analytic render vs pinned mrcs/target crop, all 9 windows × 5 frames | ≤ 1e-5 | PASS |
| N-W | the same with window coordinates +1 px in x, and separately in y, every window | > 1e-5 | rejected |
| C-K | pinned field at each logged centre vs closed form | ≤ 1e-12 px | PASS |
| PC / N-C | periodic-window offsets per window (zero + 7); mutants −μ, swapped, μ+(1,0), opposite render rejected in every window | ≤ 1e-6 px | PASS / rejected |
| C-M | continuous map vs irfft2 at all lattice points, every objective evaluated | ≤ 1e-9 rel | PASS |
| C-NEWTON | every continuous maximum converged | — | PASS |
| C-R0 | static R_fm at frame 0 | ≤ 1e-9 px | PASS |
| C-REG21 | at (2,1): R_fm and unanchored LOO iteration-1 maxima equal `attempt02.json` (`analytic_fixed_template_continuous_Rfm`, `analytic_soo_continuous`), both backends | ≤ 1e-8 px | PASS |
| C-NAT | N and K reproduce `shrinkage-attempt01.json` (rms_err, slopes, rms_known, rms_native) and accepted counts 9/8 | ≤ 1e-4 | PASS |

## 6. Execution (parent, cpu64, once each, after fresh admission; no retry)

One process, `taskset -c 62`, locks `/tmp/motioncorr-cpu64-bench.lock` + `/tmp/motioncorr-w4-analysis-cpu62.lock`
(nonblocking), CPU busy < 0.5 over 3 s, RLIMIT_AS 2 GiB, RLIMIT_FSIZE 16 MiB, output < 64 MiB, 120 s per job,
`/usr/bin/python3 -I -B`, BLAS/OMP threads 1, fresh namespace that must not exist. Expected cost: A < 5 s; B well under 1 CPU-minute.

```sh
K=/tmp/motioncorr-20261025-w4-objective-protocol/package
ssh cpu64 'cat > /tmp/run_w4_phase-30791d12.py && sha256sum /tmp/run_w4_phase-30791d12.py' < $K/run_w4_phase.py   # expect 30791d12…a6a3
# Phase A
ssh cpu64 "taskset -c 62 /usr/bin/python3 -I -B /tmp/run_w4_phase-30791d12.py A /tmp/motioncorr-w4-phaseA-$(uuidgen | tr A-Z a-z) 0eff72fec561ee064ca0065b9de875c54e9993520631bffd43e5eaff1f9dd59b" < $K/phaseA-inputs.tar
# collect NS/out/w4_fixture_diag.json and NS/RESULT.json; review the class; continue only if adoptable
$K/pack_phase_b.sh <collected w4_fixture_diag.json>        # prints the Phase B tar sha256
ssh cpu64 "taskset -c 62 /usr/bin/python3 -I -B /tmp/run_w4_phase-30791d12.py B /tmp/motioncorr-w4-phaseB-$(uuidgen | tr A-Z a-z) <PHASE_B_SHA>" < $K/phaseB-inputs.tar
```

Phase B order: decomposition v2 → shrinkage → two comparisons → oracle; it stops at the first nonzero exit.
The oracle exits 1 when a control fails, and still writes its JSON.

## 7. Limitations

- One affine realisation, noise-free, N=5, 42×32 windows, two retained global trajectories.
- No native input-fidelity witness for any patch except (2,1) (G-E 2.1e-5). R_pipe_loo models the global
  Fourier wrap and float32 frame storage, not the native float32 spectra. The eight CPU captures can later
  supply per-patch native inputs; using them is a separate, reviewed step outside this protocol.
- R_loo is the continuous stationary point of the inherited objective. The native process stops at
  RMSD < 0.5 px after at most 5 iterations, so `native − R_loo` mixes stopping with peak/quantization/float32
  arithmetic. R_loo_native_stop is reported to show the stopping share, without a gate.
- A non-converging LOO fixed point (plausible where native CUDA (2,1) diverged) is reported, not forced.
- N is at STAR print precision (≤ 5e-6 px). K uses the logged integer centre; the geometric-centre
  variant and the in-window deformation range are reported (the reviewed oracle found pure translation
  INVALID for (2,1)).
- None of this tests the fit time/zero-anchor convention, the global-stage mechanism, the applied-image
  path (no native model-1 witness) or M4 (`not_assessed`).
