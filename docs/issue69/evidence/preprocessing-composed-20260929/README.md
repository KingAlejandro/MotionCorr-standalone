# Combined preprocessing and enumeration controls — 29 September 2026

## Exact tested source

- PR 115 source: `5bda57c1f684ff59b00d50989bbc5eb6b54c6dcd`; `src` tree: `cf06f730ec033c30d63c0d89cafeff5d937eb271`.
- The evidence commit that contains this report changes documentation only.
- This tree uses the existing float-host staging; no compact uint16 production code was imported.
- Main subsequently advanced to `6393547e` through PR114. These results do **not**
  validate composition with that later main; no such combined-source run is claimed.

## Executed results

- Native CTest: **23/23 PASS**, zero failures (`ctest.log`). Test names and
  actual execution are retained, including `CudaPreprocessingFailurePaths` and
  `CudaFaultMatrix`. Hardware controls remain in the CUDA/Linux CMake block;
  CPU-only builds do not acquire a GPU test dependency.
- Production preprocessing driver: **8/8 cases PASS** — healthy uint16-input and
  float-input movies; recoverable sparse update; fatal initialization, sparse
  update, gain/sum and resident FFT; and recoverable sparse failure followed by
  fatal cleanup. The latter preserves both `updateDefectPixels` and `releaseBuffer`
  attribution. Every fatal case returns failure, publishes no MRC/STAR, performs
  no later CUDA allocation, and ends with zero owned allocations/stale releases.
  The recoverable case preserves exact complete MRC pixels/full normalized headers
  and both STAR artifacts against its healthy control.
- Production enumeration driver: **10/10 executions meet their stated outcome**.
  Runtime discovery located initialization at count call 2 and patch preparation
  at call 5. Five fatal probes fail with no image/joint STAR; healthy plus four
  recoverable/zero-device runs succeed. Each recovery matches all 14,238,980 pixels,
  full normalized MRC headers and both STAR artifacts. Original fatal return codes
  survive a cleared CUDA last-error slot; owned allocation cleanup is complete.
- Both drivers record actual payload PID/start identity/executable/CPU mask,
  exact commands, source-input-comparator-binary hashes and outcome records.

## Resource ownership and release

- Shared 4-GPU VM, device `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPUs 112–119, at most eight logical CPUs
  for all descendants; runtime `--j 4 --max_io_threads 2`.
- Every build used `-j4` under exclusive `/tmp/motioncorr-vm-build.lock`; each
  hardware run held its assigned per-device correctness lock. The other branch's
  correctness work used a disjoint GPU/CPU set. These are **not timing results**.
- CPU affinity was explicitly constrained. Memory placement used the host default;
  no allocation-locality claim follows. Host topology, disk allowance, driver and
  compiler are recorded in `host.txt`; per-payload status is retained in the drivers.
- Finished and released at 13:29:31 UTC on 29 September. Before/after compute
  records and a later empty project-lock inventory are retained. No GPU reset,
  genuine illegal access or unrelated process intervention occurred.

## Scope and preserved limitations

- Error codes are injected at actual production CUDA call sites. Genuine poisoned
  contexts and older CUDA toolkits remain untested.
- This final composition did not rerun mutants or the full 24-movie dataset.
  Existing preprocessing three-mutant discrimination was executed at `1d533d2`
  (fatal guard disabled; mutants complete and redispatch). The independent
  enumeration recording-line mutants and healthy all-24 evidence remain at their
  explicitly recorded predecessor source in `enumeration-20260929`. Neither is
  relabeled as a fresh final-tree all-24 or mutant result.
- The initial source-archive `CiFailClosedControls` diagnostic failure and the
  successful exact-Git-source retry remain in the earlier preprocessing record;
  this composed tree's suite is green without weakening the check.
- PR118's +0.230 GiB no-gain RSS regression, historical timing/resource distinctions,
  raw auxiliary-artifact failures and unrelated scientific failures are unchanged.
  These controls establish failure handling and same-backend products, not a speedup,
  scientific acceptance, or default compact-staging promotion.

## Evidence retention

`validate.sh` is the executed driver. The compressed non-image evidence archive has
SHA-256 `7c32a6073357a9eb4ca947b694178e19047484ce5e66b976f2aec80665c73942`. Full MRC/TIFF trees and binaries remain at
`/home/alex/mc-pr115-enumeration-20260929/composed-proof`
and its sibling `build` directory. They are not duplicated in Git. All image,
STAR and input TIFF hashes are in `data-sha256.json`; compact logs, comparison
reports, STAR products and process/source provenance are retained here. Initial
and final source status files are empty (clean checkouts).
