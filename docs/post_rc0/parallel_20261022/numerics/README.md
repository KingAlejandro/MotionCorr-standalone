# Composed CUDA numerics experiment, 2026-10-22

This is an experimental integration and bounded validation record for the
parent. No push, PR body, GitHub comment, Notion write or merge to main is
performed here. This record does not recommend a production merge.

## Source and composition

The isolated branch is `cuda-numeric-fixes-integration`. Its tested source is
`d751ff28594902eca75d665ff116e662653481aa`, composed by normal merges from:

- Parent / PR272: `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`.
- PR254: `b7f4517669b3eae2f7d83f767b1ef6c7bf3681ad`, merge `8e7794f9`.
- PR260: `2b23fd3cebcab116240ece1566fb7f3510423a25`, merge `c4c19418`.
- PR270: `09ee7cb0a48a3f9bc0301239af475134cb78cd6d`, merge `d751ff28`.

Issue 253/257/259 and PR254/260/270 discussions/reviews were read live before
the merges. PR267 and PR272 were also refreshed for their repaired report
contracts. Full fetched text, argv, UTC and exits are retained under `live/`.
Every assigned head matched its live PR head.

The only manual conflict resolutions concatenate both existing sections:
PR254's Hermitian native registrations and PR260's peak registrations;
PR254/260's historical acceptance-report sections; and PR260's arithmetic
host registrations with PR270's nonfinite host registration. The expanded
`mc_cuda_mutant` helper from PR254 is retained, including its include path,
Hermitian invariant and oracle expectation modes. Both CUDA production files
with independent hunks merged automatically. No numerical expression or gate
was changed beyond the assigned fixes. The focused configure checks each
mutation replacement occurs exactly once.

CPU runner, versioned generator, diagnostic checker and combined wrapper are
byte-unchanged from the pinned parent. FILE-ONLY 258/262–266/268 remain outside
this experiment. DC defaults, iteration defaults, Nyquist/crop convention,
publication policy and shared CPU arithmetic are unchanged. Production
changes are the three assigned CUDA fixes; no extra production repair was
needed. All new scripts use GPL-2.0-or-later, and no dependency was added.

The source archive is SHA-256
`7511b53c37460dcf60c8ee4c7fce2e73bef32b283a4f29a6caf9a1c674048f18`.
`live/source.json` binds the revision/tree/merge heads; `live/source-files.json`
binds every tracked file in that archive. Subsequent commits add only this
experiment's documentation and orchestration; they do not replace the tested
source identity.

## Resources and reproducibility

Remote scratch is new task-owned
`/mnt/clathrin/alex-motioncorr-parallel-20261022-numerics-d751ff28` on
`4-gpu-vm`, reached by `ssh -J ccp4-gateway 4GPUs`. Only GPU3 UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` and CPUs10–13 are assigned.
The detached driver runs under `taskset -c 10-13`; children inherit that
affinity. Compilation holds `/tmp/motioncorr-build.lock` and uses
`cmake --build ... --parallel 2`. Runtime uses `--j 1` and one numerical
library thread. Existing processes, inputs, caches and historical evidence
are preserved. No performance benchmark or timing comparison is performed. The unmodified
applications print some wall/GPU stage durations in their raw logs; those
values are retained verbatim and are not performance evidence.

`build_remote.py` builds CPU and CUDA Release configurations, sm_80,
`USE_NVCOMP=OFF`, and only `motioncorr`, three host executables and the 16
requested fixed/mutant CUDA executables. It records discovered Python,
compiler, source archive and binary identities. Remote Python is the existing
`/home/alex/.mc-venv/bin/python3` (3.12.3, NumPy 2.5.3). CUDA is the discovered
`/usr/local/cuda-12.8/bin/nvcc` (12.8.61).

nvCOMP was discovered at
`/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive` with actual
header and library. It is recorded, not enabled or qualified by this run.
The first detached driver stopped before compilation when an unnecessary
SciPy import failed. Its PID, exit 1, driver and discovery logs are retained
as `build-attempt1*`. The replacement discovery reports SciPy availability
without requiring it; no package was installed. The prior PID/exit were
reconciled before the second detached launch.

`run_remote.py` verifies the unpacked source and compiled binary hashes,
collects the exact focused CTest inventory, generates and verifies the eight
versioned fixtures, then acquires
`/tmp/motioncorr-gpu3-correctness.lock` exclusively and nonblocking. It probes
`/tmp/motioncorr-bench.lock` exclusively/nonblocking and immediately releases
the probe. Before GPU execution it checks UUID/index mapping, idle status,
absence of assigned-GPU compute apps and zero volatile uncorrected ECC. The
per-GPU lock remains held across controls, native arms and final healthcheck.
Subsequent health/app/UUID observations are recorded; any failure stops work
without a reset. The driver has durable PID and exit receipts.

## Local host controls

`check_host.py` ran with explicit
`/Users/alex.konstantinov/.local/bin/python3`, numerical threads 1, and CMake
build parallelism 2. Focused Release CTest: **6/6 PASS**
(`HermitianProjectionOracle`, `PeakFitArithmetic` and its three registered
mutants, `RealspaceBorderValidation`). Python controls: **48/48 PASS**
(diagnostics11, combined evaluator4, realistic motion13, realistic image4,
existing verdict8, existing runner8).

Nine host mutations are rejected with ordinary exit 1, after successful
compilation where applicable: interior-only, pass-through-only and combined
numeric-equality signed-zero alterations; no/actual-only/expected-only
nonfinite guards; float denominator, early store and wrong scale peak replays.
The shared border predicate passes eight finite controls and rejects all 15
nonfinite combinations. The peak replay matches all 13 exact-rational
fixtures. These are host claims; the predicate mutations do not execute a
GPU warp.

`host-receipts.tar.gz` retains 39 logs/receipts/generated mutant sources;
`host-index.json` binds each file and archive. Host binaries and their CMake
scratch remain under `build/parallel-numerics-20261022/host`, with binary
hashes in the archive. Host CTest execution is focused, not a full-suite pass.

## Native results

Both isolated Release builds **PASS**, with the exact target list and every
configure/build exit 0 in `logs/build-commands.json` inside the native archive.
Remote GCC is 13.3.0; CMake 3.28.3; CUDA 12.8.61; cuFFT 11.3.3. Production
C++ and CUDA flags are `-O3 -DNDEBUG`, with the existing OpenMP setting and
sm_80 code generation; no fast-math/FTZ override was added. CMake caches,
compile commands, target flags and linked-library listings are retained.

- **Remote host CTest: 6/6 PASS**, exit 0, with the same three executables and
  registered expectation controls listed above.
- **Native CUDA focused CTest: 16/16 PASS**, exit 0, zero skips. The four fixed
  tests are `CudaHermitianInverse`, `CudaHermitianCCF`, `CudaPeakFit`, and
  `CudaRealspaceBorderBranch`. The remaining 12 registrations are three
  inverse-site invariant mutants, four independent oracle mutants, two CCF
  invariant mutants, the float-denominator mutant, and x/y-float border
  mutants. This is a focused selection, not a full CUDA suite.
- The inverse reports **82 C2R invariant checks**, including native signed-zero
  fixtures, resident immutability, idempotence and valid-input analytic/double
  reference comparisons. Worst fixed max-relative error is
  **6.26843516934e-7**, below the unchanged 2e-6 gate. CCF reports **1,372
  C2R invariant checks** across its existing paths. The counter increments
  once per C2R call and inspects every frame within each call. Each of the four independent oracle
  mutants prints `ORACLE REJECTED MUTANT` with the invariant disabled.
- Actual peak kernel: **28/28 same-map cases PASS**, including all 13 certified
  rational fixtures and the retained nonfinite/guard classifications. The
  compiled float-denominator mutant fails the captured pedestal, exact
  pedestal and exact rounded-zero witnesses.
- Actual warp: **7/7 native cases PASS**. Each x/y-float mutant differs in its
  own three corresponding non-control cases; constant/ordinary-shift controls
  continue to match. The shared predicate's 15 nonfinite negative controls are
  host checks; no NaN was injected into a production GPU warp.
- **Eight direct native mutants reject with normal exit 1**: the five
  inverse/CCF projection-removal mutants (named invariant diagnostics), the
  float denominator, x-float and y-float. Their expected-failure registered
  CTest forms exit 0. Input/runtime exceptions are not relabelled as kills.

All 7421 archived source files and all 24 built executable hashes passed
admission verification. The CPU `motioncorr` binary SHA-256 is
`ad912663461712892c17d1cb33e92d2cee5058fc940ea11bfb438d9ca71da722`;
CUDA `motioncorr` is
`cc96a8b629d6c249f46d7f1ea8fc904c6672713c5c0e283fc2c1d4535772fe96`.
Every focused binary is separately bound in `logs/binary-hashes.json`.

GPU3 lock/probe admission occurred at **2026-10-22T14:39:48Z**. Assigned-GPU
mapping/apps/ECC were checked before and after native work; final health is
**PASS**, volatile uncorrected ECC 0, no assigned-GPU compute app, memory 1 MiB.
Both driver exit receipts are 0; the correctness lock was held through final
healthcheck and released by driver completion. The first discovery failure
remains a separate retained exit 1.

`native-receipts.tar.gz` contains **536 hash-indexed files**, including full
logs, exact inventories/argv/exits, JUnit, PID/exit receipts, source/binary
identities, both build attempts, fixture manifest and all tiny-case products.
`native-index.json` binds each file; `archive-verification.json` records local
verification of **all 536 native and 39 host receipt files** and both archive
hashes. Native archive SHA-256 is
`def6ab01874e4ff5a118feb3e307f80e6bdcee5973358cd3b0484526b3ec2435`.
The full source archive, builds, generated fixtures and original receipts
remain in the remote task scratch. Root checkout is still `c8844894`, and
its untracked `pr117-fix-measure-20260929/` remains present (read-only receipt
in `live/root-preservation.json`).

## New eight-case outcomes

**16/16 native application processes exit 0**. The checker results are **2
PASS, 10 FAIL, 4 UNIDENTIFIABLE**; this is not an aggregate science PASS.
Both checker invocations of each case have these exits: zero 0, integer 1,
fractional 1, affine 1, pedestal 1, noisy 1, flat 0, repeated 1. The wrappers exit 0
because the evaluation completed. They did not turn failed field gates into
successes. Full metrics and convergence records are in `summary.json`; all
repaired checker JSONs and original native logs/products are in the archive.

Field RMS in pixels, CPU / CUDA, with the unchanged fixed ROI:

- `zero`: **0 / 0**, accuracy PASS, sampling VALID, global converged.
- `integer`: **0.297867787 / 0.285025811**, accuracy FAIL, sampling VALID.
  CPU reaches iteration 5 with RMSD 0.923235 px; CUDA reports converged.
- `fractional`: **0.592153673 / 0.379425695**, accuracy FAIL, sampling VALID.
  CPU reaches the iteration limit; CUDA reports converged.
- `affine`: **0.454742923 / 0.323145894**, accuracy FAIL, sampling VALID,
  global converged. Local patches converge 9/9 CPU and 8/9 CUDA.
- `pedestal`: **2.39450091 / 2.39450091**, accuracy FAIL, sampling VALID,
  global converged and local patches 9/9 on each backend.
- `noisy`: **2.64741505 / 2.97844486**, characterization accuracy FAIL,
  sampling OUTSIDE_FIXED_ROI. Global alignment reaches the iteration limit
  on both backends; local patches converge 9/9 CPU and 8/9 CUDA.
- `flat`: **2.37787655 / 2.37787655**, UNIDENTIFIABLE, sampling VALID,
  global converged. This field distance is not identifiable recovery accuracy.
- `repeated`: **18.6823258 / 68.6746263**, UNIDENTIFIABLE,
  OUTSIDE_FIXED_ROI, global converged. Periodic ambiguity is retained.

In total, global convergence is 12 CONVERGED and 4 ITERATION_LIMIT. Convergence
does not establish correct recovered motion: pedestal and periodic cases
illustrate that directly. The four outside-ROI estimates retain field errors,
checker exit 1, null `signal.estimated_motion_bilinear`, and the other signal
metrics; none aborts or reuses a stale report. All 14 nonzero-case field gates
are FAIL, including the cases whose signal is unidentifiable. All fixed ROI,
truth and gate values are preserved. These are fresh environment-bound
fixtures, not a portable golden-byte equivalence claim against prior NumPy
generations. No new mathematical/scientific repair was attempted.

## Eight-case command contract and limits

The actual generator is `test-data/generate_motion_diagnostics.py`, schema
`motion-diagnostics/2`: eight 128×96×5 cases. `run_remote.py` uses the
documented `run_v2_cases.py` argv with only `--j 8` reduced to `--j 1` to
respect the assigned allocation; all `MC_DIAG_*` are absent. Existing
`max_iter=5`, seed 1, skip-defect, fixed ROI `[12:84,12:116]`, patch geometry,
truth and gates are unchanged. Each CPU/CUDA arm is a real native process.
Each native arm's argv, binary hash, exit, STAR, published non-DW sum and
log are retained.

The unmodified committed `eval_v2.py` invokes the repaired #267 checker.
Process exit 0 is not a field or science PASS. Finite estimates outside the
fixed ROI keep field errors, `OUTSIDE_FIXED_ROI`, checker exit 1 and a null
estimated-motion bilinear image metric. Noisy, unidentifiable and periodic
cases retain their separate interpretations. `summarize.py` records global
and per-patch convergence using explicit CUDA verdicts or printed CPU RMSD
against the unchanged strict 0.5 px threshold; rounded threshold equality is
reported as ambiguous. Original full logs remain authoritative.

No 100-movie census, real-movie 4096 fixture, full CUDA hardware suite,
sticky-fault/OOM campaign, nvCOMP native build, downstream science or
performance qualification is claimed. The native inverse control itself
includes a 4096² mathematical fixture. Historical failures and results keep
their source identities; no earlier suite count is transferred to this head.
