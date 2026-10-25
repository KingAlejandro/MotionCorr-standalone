# #262 four-arm CCF DC experiment: frozen endpoints and matrix

Frozen 2026-10-22 before any numerical campaign on this branch. Evidence only:
no production default, gate, tolerance or policy change, no C1 inclusion, and
no M3 decision. A later change to this file is a new, dated revision; it does
not rewrite results already produced under this one.

## Source and arms

- Base: #273 composition `805d9de27898b4a10e6212e65098d5995a40fdb1` (tested
  production source `d751ff28` plus docs), verified live 2026-10-22.
- Experiment source: `59ff5811d379bfd0f13c189fec7f54b608e61678` on
  `experiment/262-four-arm-20261022`. All native work uses a `git archive` of
  exactly this commit.
- `-DMC_EXPERIMENT_CCF_DC=ON` compiles the arms; default builds compile none of
  it. The arm is required: `MC_EXPERIMENT_CCF_DC_ARM=none|global|local|both`;
  unset or invalid aborts at the first CCF.
- Operation: zero only the disposable CCF spectrum (0,0) bin immediately before
  the CCF inverse. Sites: CPU `alignPatch` (global and local, including CPU
  retries), CUDA `cudaAlignPatchDeviceWithWorkspace` (global, per-patch local,
  windowed and the local retry path) and CUDA `cudaAlignPatchBatchDevice`
  (batched local). The selection uses each site's existing `is_global`; batched
  is local. #254's Hermitian projection and #260's FP64 fit are unchanged.
- Unchanged: movie/resident spectra, gain/defect preprocessing, weights,
  published-image DC/brightness, dose weighting, search window, tie order, the
  1e-15 guard, fit, convergence (0.5 px, `max_iter`), patch acceptance, local
  fit, nonconvergence publication behaviour.
- Witness: one stderr line at exit per process,
  `MC_EXPERIMENT_CCF_DC arm=<a> cpu.global=z/e ... cuda_batched.local=z/e`
  (zeroed/eligible CCF frames per site and stage).
- The same option compiles the verbatim #269 observation-only runtime-model
  capture (`MC_DIAG_MODEL_OUT`), needed by the unchanged truth checker.

#275 (`6ae48678`) and #276 (`1499e8ed`) were reconciled live: both CI checks
SUCCESS. Neither is merged into this branch. #275's replay is sensitivity
evidence only; #276 validates a bounded fit path only.

## Phase 0: operator and build controls (stop on any FAIL)

Builds on 4GPUs, Release `-O3 -DNDEBUG`, sm_80, `USE_NVCOMP=OFF`, under
`/tmp/motioncorr-build.lock` (nonblocking) with `--parallel 2`:
CPU-experiment, CUDA-experiment (`BUILD_TESTING=ON`), CPU-plain and
CUDA-plain (option OFF, `motioncorr` only).

`ExperimentCcfDcStage` (tests/experiment_ccf_dc_stage.cpp) prospective gates,
CPU build and CUDA build (CUDA build also covers CPU paths):

| Gate | Criterion |
|---|---|
| G1 selection | every eligible CCF frame zeroed iff the arm selects the call's stage, per site |
| G2 pedestal invariance | selected stage bit-identical across pedestals 0/1/16/256/4096 (shifts, verdict, non-DC output spectra); unselected stage must change at 4096 somewhere, else INCONCLUSIVE |
| G3 same-CCF reference | max_iter 1, uncropped CCF; independent long-double direct inverse of the identical float CCF spectrum without DC; selected stage at all pedestals and all arms at pedestal 0: max fitted-shift error <= 1e-3 px; reference margin < 1e-4 of contrast is reported as near-tie, not gated |
| G4 resident neutrality | every frame's (0,0) bytes unchanged, frame 0 byte-identical (non-batched), all arms |
| G5 scaling | power-of-two amplitude 2^-6 and 2^6 give bit-identical shifts and verdicts |

Characterization only, retained in JSON, no PASS claimed: flat/no-signal,
exact half-pixel tie, 60 px unbracketed boundary, NaN in a DC bin, NaN in a
non-DC bin. The reference is a numerical reference for the same CCF, not a
motion oracle. CCF crop (384x320, automatic downsampling) is covered by G1, G2,
G4 only, because the CPU cropped Nyquist column is #266's open input contract.

Restoring mutants, each must make the oracle exit 1 (exit 0 under
`--expect-failure`; crashes and setup errors are not kills): `cpu_restore`,
`cpu_wrong_bin`, `cpu_stage_swap`, `cuda_single_restore`,
`cuda_batched_restore`, `cuda_single_resident`, `cuda_single_stage_swap`.

Existing native tests under each arm (CUDA-experiment build, GPU2):
`CudaPatchBatch` (batched == per-patch byte exactness), `CudaHermitianCCF`
(invariant check on every C2R input), `CudaPeakFit`, `PatchRetryState`.

Default-off and none-arm controls (MRC core header 0:224, payload, STAR; log
timestamps excluded): plain vs experiment-`none` on all eight Tier A cases and
Tier B `pedestal32-s00`, `dose1-s00`, CPU and CUDA; experiment-`none` Tier A
products vs #273's retained `d751ff28` products.

## Primary endpoints: known-motion truth (Tiers A and B)

Compared with injected truth only. CPU agreement and legacy CPU output are not
criteria.

**Tier A, high-signal representable** (`motion-diagnostics/2`, #267
generator/checker unchanged): zero, integer, fractional, affine, pedestal,
noisy, flat, repeated; 128x96x5; CPU and CUDA x 4 arms = 64 processes. Argv is
#273's `run_v2_cases.py` argv (`--j 1`), with the arm variable instead of
`MC_DIAG_CCF_DC`. Evaluated by the committed `eval_v2.py`. Per case and arm:
checker status (PASS/FAIL/UNIDENTIFIABLE), checker exit, sampling status, field
RMS/P95/max px and Å, the checker's signal metrics, global/patch convergence.
#273's 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE for its `d751ff28` arms stays as
recorded.

**Tier B, matched variants** (`motion-counting/1`, #269 fixtures read in place,
hash-verified against `FIXTURE_INDEX.json`): ten conditions x seeds 0-9 x CPU
and CUDA x 4 arms = 800 processes. Conditions: pedestal 0/32 and amplitude
0.25/4 (offset/contrast), dose 0.5/1/2/4 (independent noise level), out-of-model
local field, 5760x4092 nonsquare; every condition has global and in-model local
motion. #269 argv (`--j 1`, one numeric thread). Metrics by the unchanged
`tools/check_realistic_motion.py` (runtime model) and
`tools/check_realistic_image.py` `evaluate_sum` with #272's truth caches
(SHA-256 `6b2733bd...` 4096x4096, `ff084df7...` 5760x4092).

- Accuracy: per-seed total-field RMS, P95 and max (px and Å) on the fixed
  129x129 lattice; global-trajectory RMS; local-component RMS; border lattice.
- Failure rate per arm: nonzero exit; global nonconvergence (explicit CUDA
  verdict, CPU final increment < 0.5 px, exact 0.5 ambiguous); local model
  disabled; `OUTSIDE_FIXED_ROI`; field-distance FAIL under the unchanged
  0.20/0.40/0.80 Å limits (descriptive for this family). Each component and
  their union are reported.
- Signal retention: in-band signal transfer `Re<S,T>/<T,T>`, top band
  0.12-0.16 cycles/px, FRC per band; border profile.
- Paired unit: noise seed within condition, arm vs `none` on the same backend.
  Exact two-sided sign test (ties counted and omitted), median paired delta.
  Category: improves (p < 0.05, median delta favourable), harms (p < 0.05,
  unfavourable), otherwise neutral/mixed. Exploratory and unadjusted. Failure
  union transitions use exact McNemar. Every per-seed regression is listed
  (field RMS worse at all; signal transfer lower at all), with size.
- STAR serialization loss is reported separately; it is not the primary model.

Tier B is not an S1.4 or downstream result. Counting texture without CTF,
damage or detector MTF; ten seeds share one scene per geometry.

## Compatibility diagnostic (Tier C)

Real movies have no truth. These rows are diagnostics, not M3 success criteria.

- The 60 original configurations: EMPIAR-10216, 12963, 10474 Falcon 3, ten
  movies each, 5x5 and 3x3; inputs and argv from #271's GPU ledger
  (`/mnt/clathrin/alex-motioncorr-dc-oracle/inputs/<movie>`), hash-verified
  against #271's `input-manifest.json`. e10216-01 (global nonconvergence) is
  reported as its own row and kept in every count.
- EMPIAR-10641, ten movies x 5x5/3x3 (20 configs), S1.1 sweep inputs/argv.
- Unaffected-family controls, fixed by index before any result: movies 00 and
  01 of tutorial, e10028, e10361, e10441, e10474f4 and e10164-00 (the only one),
  5x5/3x3 (22 configs), S1.1 sweep inputs/argv.
- 102 configs x CPU/CUDA x 4 arms = 816 processes. `--j 1`, otherwise the
  recorded argv.
- Clustered by movie (a movie is positive if either grid is): CPU-vs-CUDA
  product relRMSE per arm, the descriptive >= 0.1 screen and the existing
  strict 0.001 backend criterion reported separately; arm-vs-none trajectory
  (global max/RMS) and product relRMSE within backend; global convergence and
  local-model state per arm. Every regression (new screen positive, new strict
  failure, new nonconvergence or local disablement) is listed.

## Execution order, resources and retention

Order: Phase 0; Tier A; Tier B conditions in the order pedestal32, pedestal0,
contrast025, contrast4, dose1, dose05, dose2, dose4, outmodel, nonsquare; Tier
C in the order 10216 (with e10216-01), 12963, 10474f3, 10641, controls. CPU and
CUDA queues each follow this order. Rows not reached are reported UNRUN with
the reason; no subset is presented as the census.

Venue 4GPUs only. CUDA: GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`
selected by UUID, `/tmp/motioncorr-gpu2-correctness.lock` taken nonblocking and
held from first CUDA process through final health check; occupancy, UUID
mapping and ECC checked before and after. CPUs 10-13 only: CPU workers on 10,
11, 12; the CUDA worker on 13. One numeric thread per process. Fresh scratch
`/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-59ff5811`, cap 120 GiB; no
new process starts above 115 GiB. Inputs are read and hashed in place.

Retention: every STAR, log, runtime model, witness, RUN record and metric, and
every product's SHA-256. All product MRCs are retained while under the cap
(projected ~105 GiB). If the projection exceeds the cap, Tier B sums for seeds
3-9 are deleted only after their image metrics and hashes are written; this
contingency is recorded if used.

Detached workers write PID and exit receipts. A failed process is retained and
not retried in place; a repeat is a new, separately labelled iteration.

## Cost (prepared protocol; not run in this phase)

Correctness-run wall times are unqualified (concurrent shared host). The timing
protocol waits for a parent-coordinated exclusive window on 4GPUs or a
qualified cpu64 slot under `motioncorr-cpu64-bench.lock`:

- Six movies (tutorial-00/01, e10216-02/03, e12963-02/03), arms none, global,
  local, both, plus a none-vs-none null arm (two copies of the same binary).
- Warm binary and page cache with one discarded run per arm and movie.
- Balanced blocks A B C D N | N D C B A, repeated four times per movie; CUDA on
  GPU2 with an 8-CPU NUMA0 mask; CPU on cpu64 with an 8-CPU mask; THP setting
  and governor recorded.
- Report whole-movie wall and stage timers; paired per-movie median ratio vs
  none with a movie-clustered bootstrap 95% interval; the null arm bounds noise.
  A difference inside the null interval is reported as not detected, not as zero.

## Revision 2026-10-22 (iteration 2)

Iteration 1 (`59ff5811`, scratch `...-59ff5811`) Phase 0 is retained as a
mutant-control FAIL: the unmutated stage oracle passed on the CPU and CUDA
builds and 7/10 restoring mutants were killed, but `cpu_stage_swap` (CPU and
CUDA builds) and `cuda_single_stage_swap` exited 2 (the oracle raised the
wrong-stage counter as a setup error). Records: `raw/iter1-59ff5811/`.

Iteration 2 source is `3eee0a4b4e367f9b57f950c440c89679a5ec9c93`. It changes
only `tests/experiment_ccf_dc_stage.cpp`: a call counted against the other
stage is now a G1 failure (exit 1). Production sources, CMake, mutant
definitions, gates and thresholds are unchanged. Every build, Phase 0 and the
campaign are rerun from this SHA in fresh scratch
`/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b` (cap 120 GiB for
both iterations together). The endpoints, matrix and order above apply unchanged.
