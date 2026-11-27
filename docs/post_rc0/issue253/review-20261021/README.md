# PR #254 review response and boundary-injection characterization

Source tested: `30d35d41e1e35fade24e858accefda87bf0d209d` (test implementation
`cf207406`, copied-source include-path fix and characterization messages
`30d35d41`). Production code is unchanged from `8b55d5da`. This response
supersedes the earlier requirement that unprojected cuFFT input must cause a
numerical mismatch. It does not supersede the earlier product evidence.

The primary negative control is now the Hermitian invariant on the **actual
consumption buffer immediately before `cufftExecC2R`**. Test executables wrap
plan creation to retain dimensions and batch stride, then wrap C2R to download
and check every batch's x=0 and (even-width only) x=nx/2 columns. They require
exact conjugate pairing, finite values and real self-conjugate bins at y=0 and
(even-height only) y=ny/2. Exact pairing is appropriate because one projection
thread writes both members. Odd widths/heights, multiple frames, full-frame
inverses and both CCF consumers are exercised. This instrumentation is linked
only into test executables; no production or Release runtime overhead is added.

The existing shifted-spectrum fixture exercises session, host-wrapper and
dose-weighted inverses. The existing patch fixture exercises per-patch and
batched CCF inverses separately. Each compiled mutant removes only the named
site's projection. Expected-mutant mode accepts only the dedicated invariant
exception, before entering cuFFT; numerical mismatch, CUDA/setup error or an
unreached invariant is not a pass. Each mutant is also run without expected
failure mode to retain its actual failing exit and offending bin.

`cuda_hermitian_inverse --matrix` retains the 4096² unprojected numerical leak as
**characterization only**. Its raw-plan numerical comparisons cannot fail the
suite; a platform that discards the incompatible component reports that result.
The fixed production-path numerical gates remain unchanged (relative maximum
and RMS errors ≤2e-6). The ordinary CTest negative controls use the invariant,
not any behavior of invalid cuFFT input.

## Venue and commands

4GPUs (`4-gpu-vm`), NVIDIA A100 80 GB PCIe; CUDA toolkit 12.8.61,
cuFFT **11.3.3 (`11303`)**, single-precision FFTW 3.3.10, optional nvCOMP
5.3.0.16. “cuFFT 12.8” in the earlier discussion names the CUDA toolkit,
not the library version returned by `cufftGetVersion`.

Suites and raw mutants use GPU3 UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`; injections use GPU1 UUID
`GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`. Final suite, mutant and injection commands use CPUs `80-87`
(`taskset`, eight CPUs), `OMP_NUM_THREADS=8`, and Release builds. Each GPU
execution holds its matching `/tmp/motioncorr-gpuN-correctness.lock` using
`flock`; a task-local lock serializes these runs so this task holds only one GPU
at a time. Locks are released between suites and never deleted. Initial
occupancy was empty; per-run occupancy and resource identity are retained.
GPU0 became reserved by the concurrent campaign before suite execution; the
waiting commands owned by this task were stopped and validation moved to the
free GPU3 lock. No tests ran on GPU0. The superseded seven-geometry injection sweep used
CPUs `88-95`; its initial CSV is retained but is not used in the table. No
timings here are benchmark claims.

Scratch: `/mnt/clathrin/alex-motioncorr-254-review-20261021/`.
[run-suites.sh](run-suites.sh) extracts the initial `cf207406` archive;
[source-overlay.patch](source-overlay.patch) advances its code to `30d35d41`.
[resume-suites.sh](resume-suites.sh) runs that overlaid source; configure,
build and CTest exit receipts are retained separately. Every configure/build
must exit zero before execution. CTest uses `-j1 --output-on-failure
--output-junit`; no tests are excluded.
[run-mutants.sh](run-mutants.sh) records raw failing mutants and the numerical
matrix. [run-injections.sh](run-injections.sh) compiles the standalone program
with `nvcc -O3 -std=c++17 -lcufft -lfftw3f` and records its exit status.
The initial missing include-path build failure and standalone compile attempt
are retained separately from successful final runs.

## Controlled injection method

[boundary_injection.cu](boundary_injection.cu) has no MotionCorr dependency.
Inputs start at zero. Nyquist-only inserts `i` at `(kx=nx/2, ky=5)`;
DC-only inserts `i` at `(kx=0, ky=3)`; “both” inserts those two bins.
Corner controls insert only `i` at each of the four combinations
`kx∈{0,nx/2}`, `ky∈{0,ny/2}`. For 1D, ky=0 and the corner cases coincide.
Each backend receives fresh identical single-precision bytes. Both the simple
`cufftPlan2d` (1D: `cufftPlan1d`) API and the production-style rank-two,
batch-one `cufftMakePlanMany` API are measured. Inputs are out of contract;
this program characterizes implementations and has no numerical pass gate.

All inverse outputs are **unnormalized**. Define
`a(y)=cos(2π·3y/ny)` for the DC injection and
`b(y)=cos(2π·5y/ny)` for the Nyquist injection (with the injected ky replacing
3/5 for corners). Fit the difference `cuFFT−FFTW` to

```
Δ(y,x) = c_const · b(y) + c_alt · (-1)^x · a(y) + residual.
```

Inactive terms are zero; in “both”, x parity makes the two regressors
orthogonal. The proposed packing mechanism predicts `c_const=-1` and
`c_alt=-1` when their injection is present: every even sample receives
`-a-b`, every odd sample `+a-b`. A normalized 2D inverse divides this entire
expression by `nx*ny`; no fitted coefficients are renormalized here.
The retained CSV includes coefficients, residual RMS and maximum, maximum
backend difference, and two projected-input controls. FFTW(original) versus
FFTW(projected) checks effective discard of the incompatible component;
cuFFT(projected) versus FFTW(projected) checks valid-input agreement.

## Interpretation boundary

The measurements test an observable consequence of the proposed packed
complex-FFT endpoint treatment. cuFFT internals are closed: agreement supports
“**consistent with a packed real-to-complex algorithm**,” not a claim that its
source or actual execution stages have been inspected. Different dimensions
can select different implementations. A 1D 4096 result that discards the
imaginary endpoints does not contradict a leak in a selected 2D 4096² kernel.
Likewise, effective FFTW discard is an observation for these inputs/plans,
not a promise that arbitrary non-Hermitian input is supported by FFTW.
These results do not establish a scientifically preferred Nyquist/cropping
convention, downstream equivalence, or resolution of S1 trajectory divergence.

## Injection results

The table reports the production-style PlanMany fit. The simple plan API
produced the same coefficients and residuals for every measured case. The
packing hypothesis predicts **−1 for every active coefficient**; an absent
leak gives zero. Corner order is Nyquist/y=0, DC/y=0, Nyquist/y=ny/2,
DC/y=ny/2. Full precision and both plan APIs are retained in
[injection.csv](injection.csv) and [injection-summary.json](injection-summary.json).

| Width × height | Nyquist: constant | DC: alternating | Both: constant, alternating | Four corners: active coefficient | Maximum fitted residual RMS |
|---|---:|---:|---|---|---:|
| 4096 × 4096 | -1.0000002 | -0.999999795 | -1.00000021, -0.999999803 | -1, -1, -1, -1 | 2.61e-07 |
| 3710 × 3838 | -6.48654206e-11 | 9.07060008e-12 | 8.74659625e-10, -3.8920307e-09 | 0, 0, 1.62646849e-17, -1.62646849e-17 | 2.21e-07 |
| 3838 × 3710 | 0 | 0 | -1.82410167e-09, -7.32528524e-09 | 0, 0, 0, 0 | 4.81e-07 |
| 4092 × 5760 | 0 | 0 | -3.12366632e-09, -3.22440254e-08 | 0, 0, 0, 0 | 8.97e-08 |
| 5760 × 4092 | 0 | 0 | 1.67161375e-09, -2.71603509e-09 | 0, 0, 0, 0 | 1.64e-07 |
| 1024 × 1024 | 0 | 0 | 1.5639741e-08, -1.0730226e-09 | 0, 0, 0, 0 | 1.18e-07 |
| 742 × 768 | 1.21637531e-10 | 1.47644698e-11 | 7.10957151e-09, -1.36662497e-08 | 0, 0, 0, 0 | 1.99e-07 |
| 4096 × 1 | 0 | 0 | 0, 0 | 0, 0, 0, 0 | 0 |

Only 4096² follows the leakage prediction. Its isolated coefficients differ
from −1 by at most 2.1e−7; both terms superpose with residual RMS 2.61e−7
and maximum residual 1.05e−6. All four corner coefficients are exactly −1.
Across all other geometries, fitted active coefficients have magnitude below
3.3e−8. Every 1D 4096 difference is exactly zero. The largest residual RMS
outside 4096² is 4.82e−7. Thus the prediction holds for the leaking 2D
implementation, but not universally across size/plan choices.

## Per-site raw mutation results

All five raw mutants exit **1** after the invariant check fails, before cuFFT
can consume that buffer. Running them with `--expect-invariant-failure` is the
registered CTest negative control; only this invariant exception is accepted.

| Projection removed at | First failing buffer/bin (batch 0) | Raw exit |
|---|---|---:|
| Session global inverse | 4096×4096, x=0, y=1 | 1 |
| Host FFT wrapper | 4096×4096, x=0, y=1 | 1 |
| Dose-weighted inverse | 4096×4096, x=0, y=1 | 1 |
| Per-patch CCF inverse | 64×64, x=0, y=0 | 1 |
| Batched CCF inverse | 64×64, x=0, y=0 | 1 |

The CCF fixture supplies independently generated complex spectra, including
non-Hermitian boundaries; its invariant result does not rely on two alignment
paths disagreeing numerically. Fixed runs check both consumers independently
at the cuFFT boundary, even when their numerical outputs agree.

Across all 112 injections, the maximum cuFFT(projected)−FFTW(projected)
difference is 1.073e−6, and the maximum FFTW(original)−FFTW(projected)
difference is also 1.073e−6 (unnormalized unit-injection outputs). The largest
fit residual maximum is 1.909e−6, at 3838×3710 without a fitted leak. These
small residuals are reported rather than treated as exact backend equality.

## CTest fixture correction

The initial CUDA+nvCOMP full suite ran **117/118 passing, zero skips**, with
`CiFailClosedControls` as the sole failure. Its invalid-Git-ref control expected
the Git-backed error text, but the source archive had no `.git` metadata and
reported the archive-specific error instead. The checkout was then attached
to the exact tested commit with `git init`, a depth-one fetch of
`30d35d41e1e35fade24e858accefda87bf0d209d`, and `git reset --mixed FETCH_HEAD`.
`git status --porcelain` was empty; no source file changed. The failed test
passed on rerun (**1/1**, exit 0). This is 118 tests covered successfully across
the full run plus fixture rerun, **not a claim of a clean 118/118 full run**.
The subsequent CUDA-only and CPU suites use the Git-backed checkout.

For replay, start with a Git checkout at that exact revision, or attach the
same revision after applying the retained archive overlay, before running
CTest. Both the initial failure and successful single-test rerun are retained.

## Final Release suite results

| Build | Full CTest result | Exit | Skips |
|---|---|---:|---:|
| CPU | 74/74 passed | 0 | 0 |
| CUDA | 115/115 passed | 0 | 0 |
| CUDA+nvCOMP | 117/118 passed; the Git-fixture test then passed 1/1 on rerun | 8 initial; 0 rerun | 0 |

All three final configure/build pairs exited 0. Both CUDA suites passed the
fixed inverse, fixed CCF and all five expected-invariant-failure mutant tests.
The fixed CCF test checked **1,372** inverse calls; the supplemental numerical
matrix checked **64** production inverse buffers and exited 0. Each raw mutant
exited 1 at the invariant boundary, as tabulated above. The standalone
112-injection sweep built and exited 0.

[validation.json](validation.json) records counts and exit statuses extracted
from JUnit and receipts. [raw.tar.gz](raw.tar.gz) retains 74 files, including
configure/build logs, CTest/JUnit, raw mutant failures, full numerical matrix,
injection output, source/resource identities, generated mutant sources,
CMake caches, test registration and execution scripts. The nvCOMP
`LastTest.log` belongs to the final one-test fixture rerun; its full-run result
is retained in `logs/ctest-nvcomp.log` and `logs/ctest-nvcomp.xml`.
[raw-index.json](raw-index.json) records every member's SHA-256 and size.
Archive SHA-256:
`be5bb154ac10d4fe55a8ba0cc7a5457535fcaac07076cf64064d155a7cd80da6`.
The downloaded archive hash, all 74 member hashes, primary source hashes,
CSV identity, zero-skip counts, Release cache settings, build exits and raw
mutant failures were verified locally. No movie products or downstream
scientific acceptance were rerun in this review response.
