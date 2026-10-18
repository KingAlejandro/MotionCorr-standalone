# Stale CUDA error after a handled device OOM (#226 D1, register row D11)

## Result

The fix clears a recoverable pending CUDA error when a movie fails, so the next movie keeps its ingest route. On main `71ab841e`, a movie that fails with a device out-of-memory error makes the next movie in the same job lose its route (nvCOMP → compact under `--ingest auto`; CPU preprocessing on the compact route), or be refused under a pinned `--ingest nvcomp`. On the fix, every following movie keeps its standalone route and its products are identical to a standalone run. The failed movie fails as before, nothing is left on the device, and fatal handling is unchanged.

**Final D14 result for #228 (healthy-input timing, section 6): all three workloads PASS.**
- **tutL PASS:** first definitive run, upper bound +0.07%.
- **tutG PASS and e10216L PASS:** single attended confirmatory campaign, upper bounds +0.110% and +0.114% of the median main wall, medians −5.27 ms and −16.8 ms.

The confirmatory campaign supersedes the earlier UNRESOLVED results for tutG (+0.63%) and e10216L (+0.70%), which are kept below as history. The timing measures #228's own code (frozen driver source `0b11f6a8`; fix binary built from `78aae2d3`, source-equivalent), not a composition with current main.

- Source: main `71ab841e69869b615555bb02f8f393db59c22d73`; fix code `e723a737`; control `443842e9`/`78aae2d3`; CUDA-only required list `518fd61d`; temp-dir cleanup `0bc857f0`; strict control `1576a0c5`; evidence commits on top. `src/` is identical from `e723a737` on.
- Host `4GPUs`: A100 80GB PCIe `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` (GPU3), driver 570.86.10, CPUs 88–95 (`taskset`), `/tmp/motioncorr-gpu3-correctness.lock` held for every GPU run, bench lock probed before every build and GPU batch.
- Builds: Release, g++ 13.3.0, CMake 3.28.3, CUDA 12.8 sm80, nvCOMP 5.3.0.16, `-DBUILD_TESTING=ON`; recipe `raw/tools/build.sh` (from `docs/rc0/qf/tools/build.sh`).

## Mechanism

Line numbers are at main `71ab841e`.

1. `cudaAlignPatch*` checks its allocations with `HANDLE_ERROR` (`cuda_alignpatch.cu:1121` staging buffer; `ALIGN_CUDA` at `:536–543` and cuFFT plan creation at `:550` in the workspace). `HandleError` (`cuda_settings.h:51–67`) throws through `CRITICAL(ERRGPUKERN)` and never reads the last-error slot, so `cudaErrorMemoryAllocation` stays pending on the thread.
2. `run()` catches the `RelionError` per movie (`motioncorr_runner.cpp:1049`) and continues. Nothing on that path reads the slot.
3. The next movie's first `HANDLE_ERROR(cudaGetLastError())` after a kernel launch reads the stale code as its own: `cuda_movie_session.cu:2012` on the nvCOMP route ("Device ingestion failed recoverably", re-read by the host reader; refused at `motioncorr_runner.cpp:2328` under pinned `--ingest nvcomp`), `:913` on the compact route ("CUDA fused gain and sum failed. Falling back to CPU preprocessing").
4. The movie after that is unaffected: the stale code was consumed by movie 2.

A failure inside session `initialize()` never showed this, because `discard_preprocessing_session()` already reads the slot through `cudaRetryDecisionFor(failure, cudaGetLastError())`.

## Fix

`executeOwnMotionCorrection` gets a scope guard declared after `movie_session`, so it runs before the session is destroyed. Its destructor does nothing unless the function is being left by an exception (`std::uncaught_exceptions()` above its value at entry). On that path it:

1. releases the session, as `discard_preprocessing_session` does, so cleanup can record a late fatal code first;
2. decides with the existing `cudaRetryDecisionFor(session failure state, cudaPeekAtLastError())` (an empty `CudaFailureState` when there is no session, as on the streaming path in S4 below);
3. calls `cudaGetLastError()` to clear the slot only when the verdict is `CUDA_RETRY_PERMITTED`.

**Why only recoverable errors are cleared.** A poisoning code (`cudaErrorPoisonsContext`: illegal address, launch failure, ECC, …) in either the session's latched fatal state or the pending slot gives `CUDA_RETRY_FATAL`, and the guard then leaves the slot untouched: exactly what main does. The peek-then-clear order is the existing idiom in `BatchedPatchAlignmentWorkspace::decline()`. Clearing a recoverable code cannot hide a dead context in any case: a poisoned context returns its sticky error from every later CUDA call, independent of the last-error slot.

**Why the healthy path is unchanged.** Per `executeOwnMotionCorrection` call, the guard adds two `std::uncaught_exceptions()` calls (thread-local reads): one when it is constructed (`motioncorr_runner.cpp:2299`) and one in its destructor (`:2291`), which then returns on a completed movie. No CUDA call, synchronisation or `cudaGetLastError` is added to any kernel or per-movie path; nothing in `src/acc/cuda` changes. The timing comparison below measures this.

Not changed: admission (#226 D2/D3), thresholds, the per-movie failure contract, the failure messages.

## Evidence

### 1. In-product confirmation (real device OOM, VRAM balloon)

The #225 balloon (`W-QM/balloon`, sha256 `3ede9c4f…7686`, copied) holds GPU3 memory so that the measured free memory at launch is the stated value. Every job is three movies, config L (`--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --j 8 --gpu 0 --patch_x 5 --patch_y 5`), `--ingest_witness` on. Movie 1 is admitted, then patch alignment cannot allocate and the movie fails at `cuda_alignpatch.cu:1121` (error 2). Products are compared with the MRC header fields before the labels plus the full payload, and the per-movie STAR byte for byte, against a standalone run of the same movie with the same `--ingest` and no balloon (`raw/tools/grade.py`, `raw/inproduct/grade.json`).

| Job | `--ingest`, free | Movie 2: main | Movie 2: fix | Movie 3: main | Movie 3: fix |
|---|---|---|---|---|---|
| S1 e10216 → tut26 → tut27 | auto, 8.5 GiB | **compact**, "Device ingestion failed recoverably" (`:2012` out of memory), products identical | nvcomp, no CUDA error, identical | nvcomp, identical | nvcomp, identical |
| S2 e10216d → tut26 → tut27 | **nvcomp**, 8.5 GiB | **refused**, no products; job reports 2 failed movies | nvcomp, identical; job reports only movie 1 | nvcomp, identical | nvcomp, identical |
| S3 e10216 → e10164 → tut26 | auto, 8.5 GiB | compact, **CPU preprocessing fallback** (`:913` out of memory), identical; job 14.5 s | compact, no fallback, identical; job 7.9 s | nvcomp, identical | nvcomp, identical |
| S4 e10441 → tut26 → e10164 | auto, 16 GiB | **compact**, "failed recoverably", identical | nvcomp, identical | compact, identical | compact, identical |

- Movie 1 in every job, main and fix: exit 1, named alone in "Motion correction failed for 1 movie(s)" (except main S2, which also names tut26), no `.mrc`/`.star`. S1–S3 fail with a live session (session-path guard); S4 is the QM case, where the session is declined and the streaming path fails (no-session guard).
- After every job `nvidia-smi` shows GPU3 with 1 MiB used and no compute apps.
- Device memory: movie 2's own log reports the free device memory at patch alignment. In the fix runs it is 5547 MiB (tut26 after a failed movie, S1/S2), the same as tut26 after a *healthy* first movie at the same balloon level (`fix-base-b1`: 5547 MiB); the standalone value is 5551 MiB. e10164: 4353 MiB after the failed movie, 4353 after a healthy tut26 (`fix-base-b2`), 4357 standalone. The 4 MiB is retained after any previous movie, so the failed movie leaves nothing extra.
- Inputs: e10216 `FoilHole_14961495…1739_Fractions.mrc` (int16, 4096²×59); e10164 `TS_01_000_0.0.mrc` (uint8, 7420×7676×8); tutorial `20170629_00026`/`00027`; 10441 `20May09_3A-3_109-21_0003.tif`; hashes in `docs/workload_corpus/corpus.md`. **e10216d** is e10216 re-encoded as an Adobe Deflate uint16 TIFF (RowsPerStrip 1, `raw/tools/make_deflate_tiff.py`) with its few negative samples clipped to 0. It exists only to be an nvCOMP-eligible failing movie 1 under pinned `--ingest nvcomp`; its products are never compared.
- Free-memory probes (`raw/inproduct/probe-*`): e10216 fails at 8.25 and 8.5 GiB; e10216d fails at 8.5 and completes at 8.75 and 9.

### 2. Regression control `CudaStaleErrorAfterOom`

`tests/run_stale_cuda_error_controls.py` with `MC_ALIGN_ALLOC_FAULT=genuine` in the test-only `motioncorr_faultinject` shim: the first `cudaMalloc` issued from a `cudaAlignPatch*` function is replaced by a real `cudaMalloc` of 2^50 bytes, which the runtime fails and records in its own last-error slot (`pending-after=cudaErrorMemoryAllocation` is asserted). On the 48×40×6 fixture this is the global-alignment workspace allocation (`cuda_alignpatch.cu:536`). Three identical movies, fault in movie a; b and c must keep their route, show no CUDA error or fallback, match a standalone run of b, and the process must exit with no device allocation outstanding.

Product checks are strict (revised after review R-D11):
- **Inventory.** The standalone reference must contain exactly `Movies/b.mrc`, `Movies/b.star` and the joint `corrected_micrographs.star`. A faulted job must contain exactly the MRC and STAR of b and c: nothing for a, and no joint STAR, since the job failed.
- **MRC.** Each MRC goes through `docs/issue85_laneC/compare_output_trees.validate_mrc`: the full 1024-byte header with only the `Relion    <date>` writer timestamp masked (the established mask), the extended header, the payload, and the structural checks.
- **STAR.** The per-movie STAR is compared byte for byte apart from its own movie name.
- **Self-tests.** Before the fault rows, on copies of each reference tree, the comparison must reject: a flipped header byte 40 (cell dimension, the reviewer's case); a flipped payload byte; a missing STAR in the tested tree; and a STAR missing from both the reference and the tested tree. It must accept the identical tree and a timestamp-only difference.

Strict version, at the head (`raw/ctest-control/strict/`; references and self-tests pass in every run):

| Row | main `71ab841e` + shim (`443842e9`) | fix |
|---|---|---|
| nvCOMP, pinned `--ingest nvcomp` | FAIL: b refused, job names a and b | PASS |
| nvCOMP, `--ingest auto` | FAIL: b route compact, `:2012` out of memory | PASS |
| compact, `--ingest auto` | FAIL: b "Falling back to CPU preprocessing" | PASS (also on the CUDA build without nvCOMP, `--no-nvcomp`) |

Raw output: `raw/ctest-control/{ctl,fix}/`. Registered in `CMakeLists.txt` for both CUDA builds (`--no-nvcomp` without nvCOMP, which runs the compact row only).

**Required-test list.** `CudaStaleErrorAfterOom` is registered in every CUDA build (with nvCOMP all three rows; without nvCOMP `--no-nvcomp`, compact row only), and collection needs no GPU. Main had no CUDA-only section: `DEFAULT_REQUIRED_TESTS` also gates the CPU collection, where the test cannot be registered. `tools/validate_test_collection.py` therefore gains `CUDA_REQUIRED_TESTS`, applied with `--cuda` or automatically when the inspected build's `CMakeCache.txt` has `CUDA:BOOL=ON`; a `--test-dir` without a cache is an error, not a CPU verdict. Existing callers (the CPU CI job, QF `run_ctest.sh`) need no change. `tools/test_ci_fail_closed.py` restates the list and checks the missing-name rejection with `--cuda`, the complete CUDA collection, and the cache-driven selection through a real `ctest` over stub build directories (`CUDA:BOOL=OFF` passes, `ON` fails). Both checks fail on mutants (list emptied; cache detection removed). The updated validator rejects main's CUDA build ("Missing required test(s): CudaStaleErrorAfterOom") and passes the fix's CPU, CUDA and CUDA+nvCOMP builds.

### 3. Fatal path

The guard leaves the slot untouched on a `CUDA_RETRY_FATAL` verdict, and that verdict comes from the unchanged `cudaRetryDecisionFor`. No genuine device-poisoning control exists (register TST2, #213): a real sticky error cannot be produced without poisoning the context. The existing injected-code controls of the fatal paths pass unchanged on the fix: `CudaErrorClass`, `CudaResidentRetryFailures`, `CudaPreprocessingFailurePaths` (CUDA and CUDA+nvCOMP), `CudaNvcompAcceptanceFailures` and `CudaNvcompReconstructionFailures` (CUDA+nvCOMP). `CudaPreprocessingFailurePaths` also checks `remaining-owned=0` at exit after its fatal rows. No new fatal control was added, because an injected code alone never reaches the runtime slot the guard reads.

### 4. CTest

Native, 4GPUs, CPUs 88–95, GPU3 by UUID under its lock, `-j1`, `raw/tools/run_ctest.sh` (QF `run_ctest.sh` with build/source paths changed).

| Tree | Build | Result |
|---|---|---|
| fix `78aae2d3` | CPU | 70/70 passed, 0 skipped; validator PASS; `test_ci_fail_closed.py` rc 0 |
| fix `78aae2d3` | CUDA sm80 | 103/104 at first run: `ProfilingKit` failed (below); 0 skipped; validator PASS. `ProfilingKit` rerun alone: passed |
| fix `78aae2d3` | CUDA sm80 + nvCOMP | 107/107 passed, 0 skipped; validator PASS |
| **composed `8fb47a09`** (main `1afa03b5` + `1576a0c5`, merge `7ef9d4a1`; fresh batches, review round 1) | CPU (CPUs 24–39) | **72/72** passed, 0 skipped, no rerun; validator PASS; `test_ci_fail_closed.py` rc 0 |
| composed `8fb47a09` | CUDA sm80 | **106/106** passed, 0 skipped, no rerun; validator PASS |
| composed `8fb47a09` | CUDA sm80 + nvCOMP | **109/109** passed, 0 skipped, no rerun; validator PASS |
| composed `d43278e7` (`adb32785` + `78aae2d3`; superseded, diagnostic only: two `ProfilingKit` reruns exceed the runbook's one) | CUDA sm80 | 105/106 at first run: `ProfilingKit` failed (below); 0 skipped; validator PASS. `ProfilingKit` rerun alone: failed again (same two timeouts), then passed on a direct `ctest -R` rerun |
| composed `d43278e7` | CUDA sm80 + nvCOMP | 109/109 passed, 0 skipped; validator PASS |

- Fresh composed batches (`raw/ctest/composed-1afa03b5/`, `raw/tools/run_ctest3.sh`): QF `run_ctest.sh` semantics without the bench lock (4GPUs is correctness-only), at most one rerun of a runbook load-sensitive test (none was needed). Host load was recorded at the start and end of each batch: 1-min load 13.0 / 3.1 / 11.7 at the CUDA / nvCOMP / CPU starts, 0 compiler processes (`cc1plus`, `cc1`, `nvcc`, `cicc`, `ptxas`) at every start and end, 2 logged-in users. Binaries: CPU `1114b0dd…9568`, CUDA `28e2c820…a3cc`, CUDA+nvCOMP `5bcfb2dd…126f`.
- `ProfilingKit` (device-free; `tools/profiling` is not touched by this branch): every failure is the same two 30 s subprocess timeouts in `test_import_subset_boundaries`, where `mcprof run` drives a stand-in binary. It passed in the CPU batch and both CUDA+nvCOMP batches, on the fix CUDA rerun, and on the second composed CUDA rerun. Main's own source (`71ab841e`) fails the same test module on this host when other users are compiling (errors=1 with 8 `cc1plus` running); `mcprof run` first waits until no compiler runs anywhere on the host. The cause is not established: the passing direct rerun saw up to 7 compiler processes (`raw/ctest/pk-direct-compilers.txt`). Logs: `raw/ctest/ctest-*-cuda*.log`.
- Validator and fail-closed suite at the later head (`518fd61d`, CUDA-only section added; the CMake change is a comment): run from that checkout against the same build directories. Fix CPU PASS ("not required"), CUDA and CUDA+nvCOMP PASS with `CudaStaleErrorAfterOom` REQUIRED; composed `3afd6bcd` (`adb32785` + `518fd61d`) CUDA PASS with #202's `InputFormats`/`CutDownMovie` and this entry required; `test_ci_fail_closed.py` 8/8 OK on both checkouts.
- At `0bc857f0` (temporary tree removed when `--workdir` is omitted) the control was run without `--workdir` against the fix CUDA+nvCOMP binary (all rows PASS) and the CUDA binary with `--no-nvcomp` (compact row PASS, nvCOMP rows UNRUN by design); no `/tmp/mc-stale-cuda-*` directory remained (`raw/ctest/head-stale-*.txt`).
- Binary sha256: fix CPU `05fc48e5…68cc`, CUDA `6ef09b5a…4dc2`, CUDA+nvCOMP `29b894f0…c185`; composed CUDA `783cff5c…9274`, CUDA+nvCOMP `187f8675…ee62`; main CUDA+nvCOMP `c2263c22…f8dd`; main + control shim (`443842e9`) CUDA+nvCOMP built in `build-ctl-nvcomp`.

### 5. Composed tree

`git merge-tree --write-tree adb32785 <head>` is clean at `78aae2d3` (`d43278e7`), `518fd61d` (`3afd6bcd`), `0bc857f0` and `1576a0c5` (`8fb47a09`, built and tested above); main `1afa03b5` has the same tree as `adb32785`. #202 changes no `src/` file and none of the modules the new test imports (`test_gain_cache.py`, `run_nvcomp_reconstruction_controls.py`, `run_preprocessing_failure_controls.py`, `cuda_fault_inject_shim.cpp`). The names this branch adds (`CudaStaleErrorAfterOom`, `MC_ALIGN_ALLOC_FAULT`, `run_stale_cuda_error_controls.py`, `CUDA_REQUIRED_TESTS`) occur only where they are defined and used on the composed tree; no `add_test` name is duplicated. It adds no helper subcommand.

### 6. Performance

**Final: confirmatory measurement of tutG and e10216L (D14). Single attended campaign on 4GPUs GPU3, 2026-10-18, PASS for both.**
- **Design:** frozen before running (`raw/perf/confirmatory-draft/`; source `0b11f6a8`, driver `86f2db90…`, rule `077b26d1…`, launcher `44d599b9…`, manifest `ea4c9dd6…`). Fixed N: tutG 256, e10216L 176. Balanced AB/BA in two windows per workload, 16 interleaved AA nulls each, lock-holder windows ≤ 2700 s, campaign abort on any failed window. Re-checked by R-D11 through round 9 (GO-ATTENDED).
- **Operation:** run once by the coordinator as operator, attended, with no operator interventions. No WARN, OVERRUN or ORPHAN events in `operator-watch.log`; host clean afterwards.
- **What was timed:** #228's own code: main `71ab841e` (`c2263c22…`) against the fix built from `78aae2d3` (`29b894f0…`; `src/` identical to `0b11f6a8`). This is not a composition with current main.

| Workload | Label | Pairs (AB/BA) | Median fix − main | 95% CI of median | CI as % of main wall | Main / fix median wall (IQR) | AA null (16 pairs) |
|---|---|---|---|---|---|---|---|
| tutG: tutorial ×24, global, nvCOMP | **PASS** | 256 (128/128) | −5.27 ms | −14.05..+4.94 ms | −0.313%..**+0.110%** | 4.489 (0.080) / 4.483 (0.077) s | −38.4 ms, CI −98.4..+22.5 ms |
| e10216L: EMPIAR-10216 ×3, 5×5, compact | **PASS** | 176 (88/88) | −16.85 ms | −35.47..+7.36 ms | −0.552%..**+0.114%** | 6.431 (0.097) / 6.421 (0.090) s | +19.4 ms, CI −25.6..+95.9 ms |

| Window | Lock wait | Locks released after (budget 2700 s) | Worker rc | Killed at deadline | Leftovers |
|---|---|---|---|---|---|
| tutG w1 | < 0.1 ms | 1448.7 s | 0 | no | none |
| e10216L w1 | < 0.1 ms | 1303.2 s | 0 | no | none |
| tutG w2 | < 0.1 ms | 1435.5 s | 0 | no | none |
| e10216L w2 | < 0.1 ms | 1310.1 s | 0 | no | none |

- **Integrity:** every timed attempt valid (tutG 272 main, 256 fix and 16 mainb attempts; e10216L 192, 176 and 16), with 0 exit, timeout, product or resource failures and no reruns. First-pair product identity passed in every window. Every window header has `dry_run` false and GPU3 `GPU-b2cb2c39…`.
- **Independent re-check:** `combine` re-run from the committed raw ledgers and frozen manifest with the frozen driver (`raw/perf/confirmatory-4gpus/recombine/`) reproduces both campaign results **exactly** (identical JSON: labels, bounds, medians, nulls, counts).
- **Evidence:** `raw/perf/confirmatory-4gpus/` (see its README).

**History (superseded by the confirmatory campaign for tutG and e10216L; tutL's PASS stands).**

**Definitive measurement (D14 labels): 4GPUs GPU3, declared design, run once.** The maintainer accepted the 0.5% margin (D14):
- **Pass:** no resolved slowdown, and the upper 95% CI bound of median(fix − main) is ≤ +0.5% of the median main whole-job wall.
- **Unresolved:** the bound is above 0.5%.
- **Fail:** a resolved slowdown, i.e. the CI lies entirely above zero.

| Workload | Label | N (AB/BA) | Median d | 95% CI of median d | CI as % of main wall | Main / fix median wall (IQR) | AA null (16 pairs) |
|---|---|---|---|---|---|---|---|
| tutG: tutorial ×24, global, nvCOMP | **Unresolved** | 128 (64/64) | +0.000 s (+0.00%) | −0.017..+0.029 s | −0.38%..**+0.63%** | 4.563 (0.066) / 4.566 (0.078) s | replacement: −0.015 s, CI −0.123..+0.078 |
| tutL: tutorial ×24, 5×5, nvCOMP | **Pass** | 128 (64/64) | −0.013 s (−0.23%) | −0.026..+0.004 s | −0.48%..**+0.07%** | 5.448 (0.115) / 5.433 (0.077) s | +0.030 s, CI −0.043..+0.147 (replacement −0.006 s, CI −0.052..+0.081) |
| e10216L: EMPIAR-10216 ×3, 5×5, compact | **Unresolved** | 72 (36/36) | +0.001 s (+0.02%) | −0.024..+0.040 s | −0.42%..**+0.70%** | 5.802 (0.109) / 5.813 (0.079) s | +0.041 s, CI −0.083..+0.090 |

No workload shows a resolved slowdown, and all three medians are within ±0.013 s (0.23%) of zero. Two workloads are Unresolved because their pair-to-pair spread is too wide to bound the effect at 0.5%. Their pilots predicted this before the definitive runs: tutG's pilot spread of 0.244 s needed N > 128, so the design ran at the cap with an expected upper bound of 1.16%. e10216L sized N = 72 with an expected bound of 0.49%, and achieved 0.70%. Per the declared design, neither was extended.

- **Venue and lanes.** 4GPUs, A100 80 GB GPU3 `GPU-b2cb2c39…` by UUID. Payload on CPUs 88–95 (NUMA node 1); the driver, `mpstat` and `nvidia-smi` samplers on CPUs 120–123. Each window held `/tmp/motioncorr-bench.lock` and the GPU3 lock throughout:

  | Window | Start–end (UTC, 2026-10-18) | Bench-lock wait |
  |---|---|---|
  | tutG | 01:34:35–02:01:03 | 0 s |
  | tutL | 02:10:22–02:41:22 | 559 s (another worker's window) |
  | e10216L | 02:41:22–03:00:39 | — |
  | tutG replacement null | 03:00:54–03:03:57 | — |
  | tutL replacement null | 03:03:57–03:07:25 | — |

  All windows were under 45 min.
- **Builds.** The recorded identical Release sm80 + nvCOMP builds: main `71ab841e` `c2263c22…f8dd`, fix `78aae2d3` `29b894f0…c185` (`src/` identical to `e723a737` and to the head). Warm page cache, one discarded warm-up per arm. THP `madvise`. `GLIBC_TUNABLES`, `OMP_PROC_BIND` and `OMP_PLACES` unset; `OMP_NUM_THREADS=8`.
- **Design** (`raw/perf/4gpus/rule.txt`, recorded before the first timed run): a 6-pair pilot per workload, recorded in `pilot.json` and excluded from the result. N is sized from the pilot to an expected upper bound of ≤ 0.5%, with a floor of 32 and a cap of 128. The definitive phase is exactly N/2 AB + N/2 BA pairs with 16 interleaved AA′ nulls, run once. Exclusion is only for a non-zero exit or a foreign GPU3 process, rerun in the same position.
- **Integrity:**

  | Workload | Timed runs | Non-zero exits | Foreign GPU3 processes | Rejected pairs | Products |
  |---|---|---|---|---|---|
  | tutG | 302 | 0 | 0 | 0 | first AB pair identical |
  | tutL | 302 | 0 | 0 | 0 | first AB pair identical |
  | e10216L | 190 | 0 | 0 | 0 | first AB pair identical |

  Product identity uses `lib/identity.compare_trees`: full MRC header except the writer timestamp, payload, path-normalised STAR/EPS.
- **Host load** (`*/mpstat.txt.gz`, `*/nvidia-smi.csv`, `*/compute-apps.txt`, 10 s samples):

  | Window | 1-min load at start | Other CPUs busy (mean cores) | Other GPUs |
  |---|---|---|---|
  | tutG | 1.4 | 1.6 | GPU0–2 0% utilisation; one foreign process seen on GPU1, not GPU3 |
  | tutL | 12.0 | 4.5 | GPU0–2 0% utilisation |
  | e10216L | 5.4 | 1.3 | GPU0–2 0% utilisation |

  The payload lane was 20–36% busy.
- **Null defect, corrected.** The first driver named run directories after the arm label, so the AA′ null's output path contained an apostrophe. That breaks the unquoted Ghostscript command line, and the A′ arm skipped its PDF render with exit code 0. In tutG, A′ ran 0.20 s faster and used 0.51 s less CPU, giving a null median of −0.212 s, CI −0.280..−0.174, which is invalid.
  - The comparison arms were unaffected: their directories are named A and B.
  - The fixed driver (`wd11_pairs.fixed.py`) was installed at 02:02:41Z, before the tutL and e10216L driver processes started (02:10:22Z and 02:41:22Z). Their A′ CPU times match A (10.31 vs 10.23 s; 18.19 vs 18.11 s), so their interleaved nulls are valid.
  - tutG's null is replaced by a separate 16-pair window run with the fixed driver. A tutL replacement null was also run; it was not needed and is reported alongside.
  - The defective driver is retained as `wd11_pairs.defective.py`. The D14 labels depend only on the comparison CI.
- **Clarifications** (review R-D11 round 3, P3): the rule's statement that the last null block follows the last comparison block did not hold for e10216L (N = 72): its last null block came after comparison pair 64 of 72. Also, the comment in `timing4b.sh` wrongly lists tutL as having a defective null. Both are corrected in `raw/perf/4gpus/CLARIFICATIONS.md`; the executed files are unchanged. No measured value or label changes.
- **Confirmatory design for tutG and e10216L: DRAFT / NOT RUN** (`raw/perf/confirmatory-draft/`). It is ready if the maintainer chooses to run it instead of accepting D14 as unmet for #228.
- **SCARF job `3634350`** (same design; the staged driver was fixed before it could start) was cancelled while still PENDING (`QOSGrpNodeLimit`), so the result is not duplicated (`raw/perf/scarf/CANCELLED-3634350.txt`).

**Earlier exploratory measurement on 4GPUs (`mcprof compare`, superseded by the definitive run above; review R-D11 noted that tutL window 2 retained 11 AB / 9 BA pairs, which is unbalanced).**

`tools/profiling/mcprof.py compare` (docs/profiling.md), main `71ab841e` (`c2263c22…f8dd`) vs fix `78aae2d3` (`29b894f0…c185`; `src/` identical to `e723a737`). Both built by `raw/tools/build.sh`: Release, g++ 13.3.0, CUDA 12.8 sm80, nvCOMP 5.3.0.16, same CMake options. Same lane for every arm: CPUs 88–95 (`taskset`), GPU3 by UUID, THP `madvise`, `GLIBC_TUNABLES` unset, `OMP_PROC_BIND`/`OMP_PLACES` unset. The kit held `/tmp/motioncorr-bench.lock` and the GPU3 lock for each invocation (0 s waits) and settled the GPU first. Inputs on local ext4 (tutorial under `/home`, e10216 under `/mnt/clathrin`), warm page cache: one warm-up run per arm, discarded. Balanced AB/BA order, rounds with foreign CPU on the lane are discarded for both arms, round-1 products compared byte for byte (MRC header with only the writer timestamp masked, payload, path-normalised STAR/EPS). No instrumented, witness or balloon run in these windows.

- **tutG**: tutorial, 24 movies, `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp` (nvCOMP route, global only).
- **tutL**: tutG plus `--patch_x 5 --patch_y 5`.
- **e10216L**: EMPIAR-10216 int16 MRC, 3 movies (one file under three names), config L, `--dose_per_frame 1.0 --ingest compact` (compact route).

Window 2 (20 retained pairs each; d = second arm − first arm, positive = slower; CI is the distribution-free interval for the median at 95.9%):

| Workload | Comparison | Median d | CI of median | Relative | Noise | Range of d | Arm medians (IQR), s | Identity |
|---|---|---|---|---|---|---|---|---|
| tutG | fix − main | +0.021 s | −0.029..+0.101 | +0.46% | 0.114 | −0.184..+0.206 | main 4.563 (0.058), fix 4.576 (0.155) | PASS (24 MRC) |
| tutG | null main − main | +0.019 s | −0.028..+0.064 | +0.41% | 0.076 | −0.203..+0.238 | 4.568 (0.052), 4.578 (0.077) | PASS |
| tutL | fix − main | +0.004 s | −0.045..+0.024 | +0.07% | 0.068 | −0.151..+0.137 | main 5.411 (0.099), fix 5.425 (0.068) | PASS (24 MRC) |
| tutL | null main − main | +0.027 s | +0.012..+0.090 | +0.50% | 0.087 | −0.153..+0.201 | 5.417 (0.071), 5.453 (0.134) | PASS |
| e10216L | fix − main | +0.039 s | −0.065..+0.130 | +0.57% | 0.161 | −0.135..+0.232 | main 6.778 (0.087), fix 6.835 (0.162) | PASS (3 MRC) |
| e10216L | null main − main | +0.042 s | −0.006..+0.065 | +0.62% | 0.069 | −0.187..+0.196 | 6.786 (0.099), 6.830 (0.083) | PASS |

Window 1 (8 pairs, 99.2% CI = full range): tutG +0.026 s (−0.101..+0.163), null −0.020; tutL −0.028 s (−0.117..+0.101), null +0.007; e10216L +0.094 s (−0.186..+0.293), null −0.048. All unresolved, which is why window 2 used 20 pairs.

**Reading.** No comparison resolves a slowdown. In window 2 each fix−main median is within 0.03 s of its main−main null run in the same window: +0.021 vs +0.019 (tutG), +0.004 vs +0.027 (tutL), +0.039 vs +0.042 (e10216L). All three nulls show a positive median of 0.4–0.6% for the second-listed arm, and the tutL null's CI excludes zero, so a bias of that size exists in this setup independent of the code. At 95.9% the data exclude a fix slowdown larger than the CI upper bound: 0.024 s (0.44%) on tutL, 0.101 s (2.2%) on tutG, 0.130 s (1.9%) on e10216L. A smaller effect cannot be distinguished from the null with this data. This is consistent with the code argument (two thread-local reads per movie), but it is not proof of zero cost. 1–3 rounds per comparison were discarded for foreign CPU on the lane (`report.md` lists them). Raw records: `raw/perf/{perf,perf2}/<workload>-<ab|null>/` (`provenance.json`, `runs.jsonl`, `compare.json`, `identity.json`, `report.md`).

## Limitations

- No genuine sticky-error control (TST2). The fatal path is covered by the unchanged predicate, injected-code tests and the code argument above.
- The in-product OOM uses one A100 80 GB with a balloon, not a smaller card, and four three-movie sequences.
- `ProfilingKit` failed at first run in both CUDA-only batches and passed on rerun (above); its cause is not established.
- Timing (D14): PASS on all three workloads. tutL from the first definitive run; tutG and e10216L from the single confirmatory campaign, which supersedes their earlier UNRESOLVED results. Measured on #228's own code on one A100 host (4GPUs GPU3), not on a composition with current main.
- #226 D2 and D3 are unchanged and stay open.
