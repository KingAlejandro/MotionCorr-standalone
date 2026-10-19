# Qualification of the resident patch retry (#197, issue #192)

Work package W-RETRY-Q of the RC0 programme (#198). Source under test: `main` = `1db86902`
(contains #197 = `0ac2726a`). Pre-#197 reference: `0ac2726a^1` = `116eb04a`.

**Result.** The success path, the recoverable fallback, the fatal refusal, uneven grouping, the
1-worker versus 2-worker dataset and the CPU-only build all behave as specified, with strict
product identity wherever identity is required. One test gap existed (nothing reached
`downloadPatchSpectra` failure) and is closed by a test-only change in this PR; its negative
controls fail as intended. No defect in `src/` was found. Not run: see [UNRUN](#unrun).

## Setup

| item | value |
|---|---|
| host / GPU | 4GPUs, A100-PCIE-80GB (driver 570.86.10), CUDA 12.8, nvCOMP 5.3, g++ 13.3, `-O3` Release |
| lane | GPU2 `GPU-063e5232…` (`CUDA_VISIBLE_DEVICES=<UUID>`, `--gpu 0`), CPUs 80–87 (`taskset`, read back by the dataset launcher: MATCH). 2-worker runs add GPU3 `GPU-b2cb2c39…` with CPUs 72–79 |
| locks | `/tmp/motioncorr-gpu2-correctness.lock` (+ gpu3 for 2 workers, ascending) around every GPU run. `/tmp/motioncorr-bench.lock` is only checked, never taken: from `runfam3.sh` onward each run waits (60 s poll) while it is held and re-checks under the GPU lock |
| options | config L from `docs/workload_corpus/corpus.md`: `--use_own --dose_weighting --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --j 8 --gpu 0`, dose 1.0 (10641, 10216) / 1.277 (tutorial), `--gainref` for 10641 and tutorial, `--expected_frames`; ingest route recorded with `--ingest_witness` (10641: `compact`; 10216: `compact` on 1db86902, `float` on pre-#197) |
| inputs (sha256 verified) | 10641: `5f50686d…` (`…A-002_0002`), `d0a4df43…` (`…A-004_0008`), gain `bdb0bb58…`. Tutorial: `f989391b…` (00026), `fa2699a1…` (00031), gain `8919cdc7…`. 10216: `f399bd30…` (1739), `c3b841e9…` (1742). Full list: `evidence/inputs/input_sha256.txt`. All match `docs/workload_corpus/corpus.md`; 10216 was not on 4GPUs and was fetched from EBI into scratch (hashes equal cpu64's first-fetch values) |
| scratch | `/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/`; MRC outputs deleted after hashing (this PR keeps logs, STAR, JSON) |

Binaries (`evidence/evidence-binaries.sha256`; CUDA builds have `USE_NVCOMP=ON`):

| arm | source | `motioncorr` sha256 |
|---|---|---|
| **db** | `1db86902` | `7e047d19…` |
| **pre** | `116eb04a` (pre-#197) | `49cecaee…` |
| **rev** | `1db86902` with the `src/` diff of #197 reverse-applied (`patch -R`, clean). Isolates #197 from #195/#196/#178/#185/#187 | `dc627a8f…` |
| cpu-db / cpu-pre | CPU-only builds of the same two sources | `e9037126…` / `28856f94…` |
| shim | this branch (`src/` identical to `1db86902`, `git diff 1db86902 -- src` empty), `motioncorr_resident_retry_fault` | `63b173cb…` |

Identity is `compare_output_trees.py` (`docs/issue85_laneC`): manifest validation, MRC header + pixels,
all STAR, EPS and `.log` text compared; PDFs inventoried only. Timing lines are normalised; the output
root is spelled away. "Full" = complete non-PDF tree; "products" = MRC + STAR only.
Declared log allowances (dropped from both arms, in the *full* comparison only): `Staging this movie as
native` and `Released native` (#195 route lines, present only where **pre** differs), `WARNING: resident
retry preparation did not complete` and `CUDA Error in` (the injected-fallback runs). Product comparisons need none.
The 10641 inputs are staged under underscore names (`…23_00_41.tif`) because the comparator derives the
expected MRC name from the movie name while the runner replaces `.` with `_`; first-pass runs under dotted names
(`b1_e10641_*`) are kept but not comparable by the validator.

## 1. Success path (10641, 10216, config L)

2 movies per family. Retry accounting is read from the per-movie logs (a patch block with two
`[CUDA Patch Alignment] completed` lines was retried).

| family | patches | retried | retry converged | resident preparations (shim counter) |
|---|---:|---:|---:|---:|
| 10641 | 50 | **41** | 0 | **41** |
| 10216 | 50 | **30** | 0 | **30** |

- **Witness that the resident path ran.** `MC_RESIDENT_RETRY_COUNT` (new, shim only) counts completed
  `downloadPatchSpectra` invocations: 41 and 30, equal to the retried-patch counts. Second witness: peak host RSS
  drops from 7.0 GiB (pre) to 2.1 GiB (db) on 10641 because the full host movie is no longer materialised.
- **Identity, 10641 (b1u) and 10216 (b1), 2 pairs each, with null controls.** pre vs db: full + products PASS (4/4 comparisons per family).
  Null controls pre-a vs pre-b and db-a vs db-b: PASS. rev vs db (isolating #197, no log allowance needed): PASS on both families.
  shim (counter on, no fault) vs db: PASS on both. `evidence/cmp/summary_b1_b2.tsv` has 14 pairs (28 comparisons, including the recoverable runs of section 2): all PASS.
- The retry never converged in any run, so a prep error would show in products only if it made retries converge.
  The logs (RMSD per iteration) are compared, and mutant m3 below shows the comparison does fail on a wrong preparation.

## 2. Recoverable failure

`MC_PREPROCESS_FAULT=resident-retry-recoverable` (new shim mode) fails the first `cudaMalloc` inside
`downloadPatchSpectra` with `cudaErrorMemoryAllocation`, once per process. Real movies, shim binary.

| family | rc | WARNING | resident preps | products vs db | extra log lines vs db |
|---|---:|---|---:|---|---|
| 10641 | 0 | 1 (`patch (1, 1)`, "retrying from the downloaded frames") | 40 (41 − 1) | PASS (full with 2 declared prefixes; products) | the `CUDA Error … cuda_movie_session.cu:2267 : out of memory` line and the WARNING |
| 10216 | 0 | 1 (`patch (1, 4)`) | 29 | PASS | same two lines |

Compact-staged fallback (steer 1): 10641 is a u8 LZW movie on the compact route and its host staging is released
after the forward FFT. The fallback `downloadRealFrames` + `cudaPreparePatch` completed with rc 0 on both families, no
guard fired, and products were identical, on two passes for 10641 (`b2_*` and `b3a/b3b_*`).

### Memory (peak host RSS from GNU `time -v`; peak VRAM = max of NVML per-process `used_memory`, ~0.05 s sampling, one process on the GPU)

| 10641, 2 movies | peak RSS GiB | NVML peak MiB |
|---|---:|---:|
| db, normal resident retry (2 passes) | 2.07, 2.07 | 14 582, 14 582 |
| db with injected fallback, `rec` (2 passes) | 6.63, 6.67 | 15 034, 15 034 |
| pre-#197 (2 passes) | 6.99, 7.03 | 15 034, 15 034 |
| rev (1 pass) | 6.99 | 15 034 |

| 10216, 2 movies (1 pass) | peak RSS GiB | NVML peak MiB |
|---|---:|---:|
| db | 2.27 | 8 904 |
| db with injected fallback | 4.01 | 9 020 |
| pre-#197 / rev | 4.23 / 4.21 | 9 172 / 9 172 |

- Falling back materialises a full float host movie: +4.6 GiB on 10641 and +1.7 GiB on 10216, i.e. the same as pre-#197. The
  injection is once per process, so these runs mix 40 resident retries with one fallback; the RSS peak is set by the fallback.
  (pre/rev 10216 differ from db partly through #195's compact staging; rev shows the #197 effect alone: 4.21 → 2.27.)
- Extra device allocation of one resident retry (`cudaMalloc` trace from the shim, unwindowed `d_Ipatches` + `d_fpatches`):
  10641 (70 groups) 263 854 080 + 264 312 160 B = **504 MiB**; 10216 (59 groups) 157 913 264 + 158 299 360 B = **301 MiB**.
  Whole-run NVML peak with the resident retry is **not higher** than without it (10641: 14 582 vs 15 034 MiB, 10216: 8 904 vs
  9 172 MiB); the peak is set elsewhere, and the pre-#197 upload path peaks higher. Limits: NVML sampling can miss sub-100 ms
  transients, and these are whole-run peaks, not a per-stage trace.
- The R-DESIGN estimate for 144-group 4K EER (~580 MiB) was **not measured**. Scaling the 10216 allocation sizes linearly to
  144 groups gives about 736 MiB (calculated, same patch geometry assumed). UNRUN as a measurement.

## 3. Fatal failure

`resident-retry-fatal` returns `cudaErrorIllegalAddress` from the same allocation (returned code, no device is poisoned).

| family | rc | message | products |
|---|---:|---|---|
| 10641 | 1 | `CUDA device context is unusable for Movies/HM70-1_10-A-002_0002_… (patch 1, 1): an illegal memory access was encountered. Refusing to retry alignment on a poisoned context.` | none: no MRC, no per-movie STAR, no joint STAR |
| 10216 | 1 | same, `(patch 1, 4)` | none |

The second movie of the same process is then refused at session initialisation ("CUDA device became unusable during session
initialization … Refusing CPU fallback after a fatal device error"), the existing #69 contract for a retired context. The shim reports
`remaining-owned=0 stale-releases=0` (no leaked device allocation) in every shim run.

## 4. Dataset level (`tools/multi_gpu/run_dataset.py`)

Mixed STAR, 4 movies, 2 optics groups, no gain: `[tutorial 00026, 10641 A-002, tutorial 00031, 10641 A-004]`; contiguous
sharding gives w0 = (t26, 10641-A), w1 = (t31, 10641-B). 10641 retries 25/25 and 16/25 patches in this batch.

| run | binary | verdict | notes |
|---|---|---|---|
| `d1` 1 worker (GPU2) | db | PASS, `dataset_ready` | baseline |
| `d2` 2 workers (GPU2+GPU3) | db | PASS, `dataset_ready` | **identical to d1**: 30 files, 4 MRC (bytes `[0:224]`+`[1024:]`), STAR incl. joint, EPS text, per-movie logs; PDF/`.lst` inventory only |
| `dshim` 2 workers | shim, count only | PASS | identical to d1; counter 25 + 16 resident preparations |
| `dpoison` 2 workers | shim, `resident-retry-fatal` only in the worker whose `CUDA_VISIBLE_DEVICES` contains GPU3 | **FAIL**, `dataset_ready=false`, `failure: Worker phase exited 3` | per-worker return codes `[0, 1]`; GPU witness: w0 on GPU2, w1 on GPU3, 2 distinct devices; w1 log carries the refusal for 10641-B; **no `merged/` tree and no dataset joint STAR**; retained: w0 complete (t26, 10641-A MRC + STAR + its own per-worker joint STAR) and w1's healthy `t31` MRC + STAR; no product for 10641-B |

The comparator is `scripts/cmp_tree.py` (the repo comparator takes one expected shape and cannot validate a tutorial + 10641 tree).
Differences it excluded as telemetry: the two `Batched patch alignment … free device memory / rose by at most` lines differ by 4 MiB
between runs. This tool, not the repo comparator, was used for the dataset
check; its null control (`d1` vs `d1`) is clean, and mutant arms (section 5) do fail the repo comparator.

## 5. Unequal grouping (steer 2) and negative controls

CLI: `--group_frames N`. Note the runner (`src/motioncorr_runner.cpp:2172-2181`) puts the remainder in the **last** groups, so a non-dividing value gives
a *larger* last group, not a short one. `--group_frames 4`: 70 frames → 17 groups (last two of 5); 59 frames → 14 groups (last three of 5).

| family, `--group_frames 4` | retried / 50 | resident preps | pre vs db | rev vs db | shim vs db |
|---|---:|---:|---|---|---|
| 10641 | 9 | 9 | PASS (full, products) | PASS | PASS |
| 10216 | 25 | 25 | PASS | – | PASS |

Negative controls (mutants of `1db86902`, strict comparison against db, 10641, grouping 1 and 4):

| mutant | defect | `--group_frames 1` | `--group_frames 4` |
|---|---|---|---|
| m3 | `downloadPatchSpectra` copies group 0's spectrum to every group | **FAIL** (full 7 files, products 3; every retry now "converges", 41/41) | **FAIL** (4 files; 9/9 retries converge) |
| m4 | `downloadPatchSpectra` ignores `group_size` (uses `group_size[0]`) | PASS (cannot see it: all groups have size 1) | **FAIL** (full 4, products 2) |

So the grouped run is what discriminates m4, and the success-path run discriminates m3.

## 6. CPU-only

10641 L, CPU backend, CPUs 80–87, `--j 8`, `OMP_NUM_THREADS=8`, 2 movies: cpu-pre vs cpu-db, full + products **PASS** (1 pair, no null control; rc 0 both, peak RSS 14.2 / 13.6 GiB).
The CPU path does not use #197; this shows no regression on it. Timings are not compared.

## 7. Coverage of items 2–3 by existing tests, and the gap

| test (CTest) | what it reaches | reaches `downloadPatchSpectra` failure? |
|---|---|---|
| `PatchRetryState` | `alignPatch` shift accumulation, device-free | no |
| `CudaFaultMatrix` | `CudaMovieSession` and `cudaAlignPatchDevice` directly (`preparePatchInVram` included), not the runner | no (does not call `downloadPatchSpectra`) |
| `CudaErrorClass` | retry-verdict predicate over `CudaFailureState` | no |
| `CudaPreprocessingFailurePaths`, `CudaNvcompReconstructionFailures` | runner via the fault shim | no. `patch-prep-recoverable` fails `preparePatchInVram`, i.e. the pre-#197 fallback arm; it is not registered (documented as never firing on the 48×40 fixture) |
| `motioncorr_retry_caller` (not a CTest; used by `tools/single_gpu/run_*`) | forces a non-converged resident attempt, so the resident retry **success** path runs | no |

Gap: no test failed the new step, so neither the WARNING/download path nor the fatal refusal inside the resident retry block was covered.

Added (test-only, no `src/` change): `CudaResidentRetryFailures` = `tests/run_resident_retry_controls.py` driving a new
`motioncorr_resident_retry_fault` (retry-caller shim + fault shim linked together) on a 512×512×12 synthetic uint16 TIFF, 3×3 patches.
New shim modes: `resident-retry-recoverable|fatal` (fail the first `cudaMalloc` called from `downloadPatchSpectra`), `MC_RESIDENT_RETRY_COUNT`,
`MC_FAULT_ONLY_CVD` (inject in one worker only). It asserts: healthy (one resident preparation, retry converges, products), recoverable
(WARNING, zero resident preparations completed, pixels identical, no leak), fatal (refusal text, non-zero exit, no products, no later CUDA allocation).

Results on 4GPUs, GPU2: `ctest` on this branch for `PatchRetryState`, `CudaFaultMatrix`, `CudaErrorClass`, `CudaPreprocessingFailurePaths`,
`CudaPatchBatch`, `CudaResidentRetryFailures`, `CudaNvcompReconstructionFailures`, `CudaNvcompAcceptanceFailures`: **8/8 pass**
(`evidence/ctest/ctest-branch.log`). Runner mutants of the new test: m1 (resident block never refuses) fails with `fatal: refusal missing`;
m2 (failed preparation treated as done) fails with `recoverable: owned CUDA allocation cleanup was not complete` (the run dies before the
shim's exit report). The unmutated binary passes. Full CTest inventory is not run here (that is W-QUAL's Q1); `CiFailClosedControls` needs git metadata and was not run.

## UNRUN

- Measurement of the unwindowed-prep VRAM on 144-group 4K EER (only the 10641 / 10216 allocations are measured).
- 10474 Falcon 3 and 12963 EER, `--even_odd_split --save_noDW` arms: covered by #197's own evidence, not repeated.
- A retry that converges on real data (none did in any run here); the synthetic CTest covers a converged retry.
- A physically poisoned context: all fatal cases are injected return codes.
- Timing claims: runs shared the host with other lanes and, for the first batches, with builds. Only identity, counters, RSS and NVML peaks are claimed.
- 2-worker mixed batch with a gain reference (a single `--gainref` cannot fit both families).

## Process notes

- Runs `b1*`, `b1c*` and `b2*` started before the bench-lock steer and may have overlapped other lanes' work; they claim no timing. Everything from `b3*`
  on (RSS/VRAM, grouping, mutants, dataset, CPU, driver runs) ran through the wait-and-recheck wrappers.
- A temporary in-place `patch -R` tree and mutant trees live only in scratch; the mutations are in `scripts/mkmut.sh` and `scripts/mkmut2.sh`.
- Harness scripts are in `scripts/`; raw run side files (stdout/stderr, ingest witness, NVML samples), comparator JSON, ctest logs and `summary_runs.json` are in `evidence/`.
  `runfam2.sh` used by the early batches is `runfam.sh` with the `e10641u` case; `runfam3.sh` adds the bench wait and NVML sampler.
