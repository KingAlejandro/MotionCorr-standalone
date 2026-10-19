# Native qualification of main `1db86902` (RC0 baseline) — W-QUAL, issue #198 (Q1)

Source under test: `1db869025507ac801845b4001b84e6bc0e77a645` (clean `git clone` + checkout on 4GPUs, 0 modified files). Reference for the #178 path: `d7171b810dc97003784339d7bad1c279903f3bba`.
Host: 4GPUs (`4-gpu-vm`), 4× A100 80GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, nvCOMP 5.3.0.16, CMake 3.28.3, Python 3.12.3 + numpy 2.5.3 (`~/.mc-venv`), Ghostscript 10.02.1, THP `madvise`. All builds Release (`-O3 -DNDEBUG`, verified in `flags.make`).
Lane: GPU1 (`GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`, selected through `CUDA_VISIBLE_DEVICES=<UUID>`, same silicon as index 1) and CPUs 104–111 (`taskset -c 104-111` on every build, test and run). The multi-GPU step used CPUs 104–111 + 64–71 with the four correctness locks and the bench lock held. Before every GPU run, CTest batch and build, `flock -n /tmp/motioncorr-bench.lock true` was checked and polled every 60 s when held. This is a **correctness** qualification: no timing or speed claim is made.

## Result

| Item | Verdict |
|---|---|
| 1. Builds (CPU, CUDA sm80, CUDA sm80 + nvCOMP) | 3/3 built, rc 0 |
| 2. Full CTest, no exclusions | CPU **58/59** (`ProfilingKit` failed once on a 30 s subprocess timeout under host load, **passed on rerun**); CUDA **89/89**; CUDA+nvCOMP **92/92**; 0 skipped. `CiFailClosedControls` **passed** in all three (real git checkout). `MultiGpuScheduling` passed first time and on the rerun in all three. |
| 3. Route invariance, 7 families × G/L = 14 cases | `--ingest auto` vs `--ingest float`: products (MRC header+payload, STAR) identical in **14/14**; 14/14 CPU-build runs and 28/28 CUDA runs exited 0. Strict all-files identity differs only by route-record log lines (PASS with declared route-log allowance; `e10028`, where both routes are float, is strictly identical with no allowance). |
| 4. #178 CPU unweighted path in CUDA builds | Reached and executed natively; **6/6** cases strictly identical to the pre-#178 CUDA build; **injected non-fatal device failure → CPU fallback inside a `--gpu` run** also identical (CUDA build vs pre-#178 build). |
| 5. Multi-GPU publication | 1/2/4 workers on the 24 tutorial movies, G and L: dataset endpoint PASS in 6/6, products identical across worker counts and to a single-process run (6 pairs per config, with a discriminating positive and negative control). Mixed-format 2-worker dataset (tutorial + 10641 + EER) PASS, identical to its 1-worker run. |

Not a gate result: CPU-vs-CUDA `--gate backend` is a diagnostic (below). Nothing was relaxed; no source file under `src/` was changed.

## 1. Builds (`raw/summaries/build-info.txt`)

| config | CMake | binary sha256 (`motioncorr`) | `ctest -N` |
|---|---|---|---:|
| CPU-only | `-DBUILD_TESTING=ON -DCUDA=OFF` | `dd86cd41…6b26439` | 59 |
| CUDA sm80 | `-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=OFF` | `8dd18695…59b3` | 89 |
| CUDA sm80 + nvCOMP | as above with `-DUSE_NVCOMP=ON -DNVCOMP_ROOT=~/nvcomp53/…` | `77db3f92…12a99` | 92 |
| pre-#178 reference `d7171b81` CUDA+nvCOMP | `BUILD_TESTING=OFF` | `1d5d0d1e…ebf1` | – |
| pre-#178 CPU (control) | `BUILD_TESTING=OFF -DCUDA=OFF` | `c30b11c2…d73e` | – |

Fault-injection binaries (`motioncorr_faultinject`, from the same sources): `c808db08…6852` (1db86902), `a8671c76…9d74` (d7171b81). Full hashes in `build-info.txt`. `validate_test_collection.py` reported PASS for all three collections.

## 2. CTest (`raw/ctest/`)

| config | collected | passed | failed | skipped | exit |
|---|---:|---:|---:|---:|---:|
| CPU | 59 | 58 | 1 (`ProfilingKit`) | 0 | 8 |
| CUDA | 89 | 89 | 0 | 0 | 0 |
| CUDA+nvCOMP | 92 | 92 | 0 | 0 | 0 |

Per-test results: `raw/ctest/ctest-<cfg>.summary.json` (from the JUnit files). CTest ran from the real clone (`.git` present), so `CiFailClosedControls` passed (21–26 s) and no failure needs explaining.

- **`ProfilingKit` (CPU)**: two errors in `tools/profiling/tests/test_import_subset_boundaries.py` (`MultipleStarLoops` cases), both `subprocess.TimeoutExpired` on an `mcprof.py run` call. The test's `cli()` helper uses a hard `timeout=30` (`test_import_subset_boundaries.py:24`); host load average was ≈27 from other sessions. Reruns: CPU `ProfilingKit` **passed** (115.9 s, `raw/ctest/ctest-cpu-rerun.log`); it also passed in the CUDA and nvCOMP runs (130.7 s, 121.7 s). Classified as a load-sensitive test, not a product defect.
- **`MultiGpuScheduling` (0.25 s timing flake)**: first run passed in all three (114.9 / 106.5 / 92.9 s), rerun passed in all three (87.5 / 97.9 / 96.6 s). The flake did not occur.
- **Aborted attempts retained**: my first CUDA and nvCOMP CTest runs were stopped (my own processes only) when W-EER-DEV held the bench lock; partial logs are `ctest-cuda-ABORTED-bench-lock-held.log` and `ctest-nvcomp-ABORTED-bench-lock-held.log`. They are not counted. The reported CUDA/nvCOMP runs started after the lock gate was added.
- New-in-composition tests present and passing: `CpuUnweightedStream` (#178, Linux allocation witness active), `FloatPlanCache` (#187), `LogfileFromEps*` (#185), `SignedMrcStaging` (#195, CUDA configs), `NativeMovieStaging`, `CudaU16StagingEquivalence`, `PatchRetryState` (#197). nvCOMP build adds `CudaAdler32`, `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`.

## 3. Route-invariance product campaign (`raw/summaries/campaign/`, `raw/campaign-run-logs/`)

One movie per family, `docs/workload_corpus/families.json` options (config G global, L `--patch_x 5 --patch_y 5`, `--use_own --dose_weighting --dose_per_frame <fam> --bfactor 150 --seed 1 --expected_frames <n> --j 8`, gain/EER options per family), `--gpu 0 --ingest_witness`. Movies: tutorial `20170629_00026`, 10361 `…103-12_0007…`, 10474-F3 `2019-06-21_20-39-45.801`, 12963 `…014501_EER`, 10216 `…1739_Fractions`, 10028 `031_movie`, 10164 `TS_01_000_0.0`. All 7 movie SHA-256 (and the tutorial and 12963 gains) match `docs/workload_corpus/corpus.md` (`raw/summaries/campaign/inputs.json`). 10164 and 10216 were not on 4GPUs and were re-fetched from EBI into scratch; sizes and hashes match. Input links use `.`→`_` stems (e.g. `PS_18_2_4_…`), because the runner writes products under that spelling; file bytes are the source files.

Comparator: `docs/issue85_laneC/compare_output_trees.py` (the brief names `tools/compare_output_trees.py`, which does not exist on main). Declared route-record log prefixes: `nvCOMP ingestion`, `Staging this movie as native`, `Released native uint`, `Materialized native`, plus `Released native int` (see PASS\* note). One arm took a different route in every case except 10028, so the route log lines differ by design.

**Route invariance** (nvcomp build, `--ingest auto` vs `--ingest float`; CPU-only build for the diagnostic):

| family | cfg | auto route | float route | CPU build route | products-only identity (MRC hdr+payload, STAR) | strict all-files | route-log allowance (declared prefixes) | other log diffs | peak RSS auto / float / CPU (GiB) |
|---|---|---|---|---|---|---|---|---:|---|
| tutorial | G | nvcomp | float | float | PASS | differs (route log lines) | PASS | 0 | 0.34 / 1.52 / 2.71 |
| tutorial | L | nvcomp | float | float | PASS | differs (route log lines) | PASS | 0 | 0.34 / 1.52 / 2.84 |
| e10361 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 1.54 / 5.67 / 11.06 |
| e10361 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 1.53 / 5.68 / 11.28 |
| e10474f3 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 3.16 / 5.02 / 8.53 |
| e10474f3 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 3.16 / 5.14 / 8.65 |
| e12963 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 2.30 / 3.57 / 5.89 |
| e12963 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 2.30 / 3.63 / 5.97 |
| e10216 | G | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 2.10 / 3.89 / 7.50 |
| e10216 | L | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 2.10 / 4.01 / 7.66 |
| e10028 | G | float | float | float | PASS | PASS | PASS | 0 | 1.59 / 1.55 / 2.11 |
| e10028 | L | float | float | float | PASS | PASS | PASS | 0 | 1.54 / 1.58 / 2.43 |
| e10164 | G | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 0.80 / 2.14 / 3.78 |
| e10164 | L | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 0.85 / 2.08 / 4.60 |

`PASS*` = the comparator, run with the four prefixes declared in advance, still reports a log difference, but the retained logs show the only extra lines are the signed/int route record `Released native int16/int8 host staging after device forward FFT.` (added by #195; prefix `Released native int`); there are no other log differences (column "other log diffs" counts lines outside the extended prefix list).


### CPU-only build vs CUDA `auto` (item 3, `compare_motioncorr.py --gate backend`, DIAGNOSTIC ONLY)

Backend thresholds: shift RMS 0.02 px, max shift 0.05 px, image RMSE 0.020, max pixel error 5, relative RMSE 0.001 (nonblocking diagnostic).

| family | cfg | gate exit | shift RMS px | max shift px | image RMSE | max pixel err | relative RMSE |
|---|---|---:|---:|---:|---:|---:|---:|
| tutorial | G | 0 | 0.0049 | 0.0075 | 0.007547 | 0.04633 | 0.007096 |
| tutorial | L | 0 | 0.0049 | 0.0075 | 0.007233 | 3.007 | 0.008358 |
| e10361 | G | 1 | 0.0070 | 0.0149 | 0.2781 | 1.662 | 0.01095 |
| e10361 | L | 1 | 0.0070 | 0.0149 | 0.1814 | 44.86 | 0.009091 |
| e10474f3 | G | 0 | 0.0104 | 0.0159 | 0.01477 | 0.08318 | 0.01555 |
| e10474f3 | L | 1 | 0.0104 | 0.0159 | 0.4403 | 4.368 | 0.5999 |
| e12963 | G | 1 | 0.0172 | 0.0316 | 0.02191 | 0.2836 | 0.02273 |
| e12963 | L | 1 | 0.0172 | 0.0316 | 0.3783 | 5.819 | 0.499 |
| e10216 | G | 1 | 0.0166 | 0.0327 | 0.3937 | 2.342 | 0.01659 |
| e10216 | L | 1 | 0.0166 | 0.0327 | 9.097 | 97.29 | 0.4344 |
| e10028 | G | 1 | 0.0032 | 0.0074 | 5.983 | 28.27 | 0.01392 |
| e10028 | L | 1 | 0.0032 | 0.0074 | 5.667 | 1030 | 0.01401 |
| e10164 | G | 0 | 0.0009 | 0.0014 | 0.006514 | 0.05032 | 0.001494 |
| e10164 | L | 0 | 0.0009 | 0.0014 | 0.004267 | 3.063 | 0.001252 |


Reading the tables:
- Routes are the `--ingest_witness` lines. After #195/#196: tutorial → `nvcomp`; 10361/10216/10164/EER → `compact` (EER and MRC modes 0/1/6 were `float` at `116eb04a`); 10028 float32 MRC → `float`.
- The strict all-files comparison reports a difference for every case where routes differ; it is the route-record log lines (one line per route, e.g. `nvCOMP ingestion: …`, `Staging this movie as native unsigned 16-bit; …`, `Released native uint16 host staging after device forward FFT.`) plus the output-path line. With the allowance, 10 of 14 pass directly. For 10216 and 10164 the signed/int8 route line `Released native int16/int8 host staging after device forward FFT.` (new in #195) is not in the prefix list I declared in advance; the retained logs show no other difference, so I list them as `PASS*` rather than silently widening the first verdict. The comparator's `--allow-added-log-line` list needs `Released native int` for signed MRC routes.
- The CPU-vs-CUDA table is the **requested diagnostic**. Relative RMSE fails in all 14 cases as expected. In addition, the absolute image-RMSE gate (0.020) fails in 9 of 14 cases (10361 G/L, 10474-F3 L, 12963 G/L, 10216 G/L, 10028 G/L; 12963 G is marginal at 0.0219) and max-pixel-error (5) in 5 (10361 L, 12963 L, 10216 L, 10028 G/L; 1030 on 10028 L); the global shift gates (0.02 / 0.05 px) are met in all 14. 10028's images have a large dynamic range, so absolute RMSE scales with it; the 0.43–0.60 relative RMSE in 10216 L, 10474-F3 L and 12963 L is the largest. **Inheritance control** (`raw/summaries/inherited_control.json`): for 10216 L and 12963 L the current CPU build is byte-identical to the pre-#178 CPU build, and the current CUDA build to the pre-#178 CUDA build (`--ingest auto`), so the divergence is not introduced by this composition. The other 12 cases have no such control; I make no claim about them beyond the diagnostic. No gate was edited.
- Peak RSS is from `/usr/bin/time -v` of the worker process (single movie): the compact/nvCOMP routes use 0.2–0.65× the float route's RSS in every case where they differ.

GPU identity: the CUDA_VISIBLE_DEVICES=UUID pin applies to every run. My first nvidia-smi sampler matched the pid of `/usr/bin/time` rather than the forked payload, so **none of the 42 first-pass GPU runs recorded a physical-GPU witness** (`gpu_witness.pid_hits = 0` in their JSON). I fixed the sampler (descendant-aware) and re-ran three campaign cases through the same code path: all three witnessed on `GPU-cd5b9f86-…` only (`raw/summaries/gpu_witness_check.json`). The multi-GPU runs were witnessed by the launcher's own witness (4/4 workers on their intended distinct UUIDs).

Superseded: a first campaign attempt looked for products under the dotted stem and read "no product" although the runs exited 0; it was stopped after 3 cases, logs kept as `raw/logs/campaign-attempt1-stem-bug.out` and `raw/summaries/campaign-superseded/`. All 14 reported cases are from the corrected rerun.

## 4. #178: when the CUDA build takes the CPU unweighted path (`raw/summaries/fallback178/`)

From `src/motioncorr_runner.cpp` (`executeOwnMotionCorrection`, ~3955–4030): `pre_dw_sum_needed = !do_dose_weighting || save_noDW || even_odd_split` (3355). Then:

1. resident session present → `CudaMovieSession::reconstructUnweighted`; if it returns false non-fatally → CPU `sumUnweightedFrames` (the #178 function);
2. `use_gpu` without a session → `cudaRealSpaceInterpolation`; non-fatal false → CPU path;
3. no `--gpu` (a CUDA build running on the CPU backend) → CPU `sumUnweightedFrames` directly.

A fatal device error refuses the fallback instead (`refuse_fallback_if_fatal`). CPU witness in the log: `Summing frames before dose weighting: ….. done` (one dot per frame, 23 for the odd case); the device path logs `Summing frames before dose weighting (CUDA in-VRAM)...`.

**A — CUDA+nvCOMP build of 1db86902 vs CUDA+nvCOMP build of d7171b81, both without `--gpu`**, tutorial movie 00026, `tools/profiling/lib/identity.py` (MRC header+extended header+payload, STAR/EPS after root normalisation, same inventory; logs and PDFs excluded by that comparator):

| case | options beyond family G/L | CPU witness (cur / pre) | MRC compared | strict tree identity |
|---|---|---|---:|---|
| noDW-G | `--save_noDW` | 1 / 1 CPU lines, 0 / 0 CUDA | 2 | PASS |
| noDW-L | `--save_noDW` | 1 / 1 CPU lines, 0 / 0 CUDA | 2 | PASS |
| evenodd-G | `--save_noDW --even_odd_split` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| evenodd-L | `--save_noDW --even_odd_split` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| evenodd-23fr-L | `--save_noDW --even_odd_split --last_frame_sum 23` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| nodose-G | `(no --dose_weighting)` | 1 / 1 CPU lines, 0 / 0 CUDA | 1 | PASS |


For contrast the 1db86902 build with `--gpu 0` printed the CUDA line and no CPU line in `noDW-G` and `evenodd-G` (`curgpu`), i.e. the device path does not execute #178's function. That contrast compares log lines only, not products.

**C — injected non-fatal device failure inside a `--gpu` run** (`fallback178_injected.py`, repo shim `tests/cuda_fault_inject_shim.cpp`): `MC_FAULT_ORDINAL=k` returns `cudaErrorMemoryAllocation` for the k-th `cudaMalloc` (a recoverable class). A trace run counted 19 `cudaMalloc` calls; sweeping k=1…16 stopped at **k=16**, where the log shows `Summing frames before dose weighting (CUDA in-VRAM)...` followed by `Summing frames before dose weighting: ........................ done` (CPU path), rc 0, with `--save_noDW --even_odd_split`, tutorial G. The same k with the pre-#178 fault-injection build produced the same two lines, and the four product MRCs (+ STAR/EPS) are identical (`identity.compare_trees`: 4 MRC compared, no differences). The earlier k=1…15 runs completed rc 0 without reaching that path (other recoverable fallbacks) and are listed in `injected.json`. The injected code is a status returned by an interposed call; it is not a real out-of-memory event and not device poisoning.

Limits: tutorial movie only; global and 5×5 local; one odd-frame selection (23 frames); no GPU-vs-CPU product comparison (not an invariant); wall times in the JSON are incidental.

## 5. Multi-GPU publication (`raw/summaries/multigpu/`, `raw/multigpu-run-logs/`)

All four correctness locks + the bench lock held ≈3 min per invocation (`multigpu_step.sh`: ascending gpu0–gpu3, bench last, foreign-process wait). Fixed aggregate budget of 16 CPUs (104–111 + 64–71): w1 `64-71,104-111` j16 on GPU1; w2 `104-111;64-71` j8 on GPU1,GPU2; w4 four 4-CPU masks j4 on GPU0–3. Options: `--use_own --dose_weighting --dose_per_frame 1.277 --gainref Movies/gain.mrc --ingest auto`, config L adds `--patch_x 5 --patch_y 5`. A single-process single-GPU run (`s0`) is the reference.

Per arm (G and L, w1/w2/w4; 6/6 pass): `dataset_status` verdict PASS with `dataset_ready`, `workers_complete`, no process-ownership errors, "No observed live PID/birth descendants"; `aggregate.json` PASS; worker status PASS with **every worker pid witnessed on its intended distinct UUID** (w4: 4/4 distinct); the shard manifests partition the 24 movies disjointly and each worker's products equal exactly one shard (6/6/6/6 or 12/12 or 24); merged tree has 24 MRC + 24 STAR; the joint `corrected_micrographs.star` has 24 rows in input order, all paths inside the published root, and the per-worker aggregates are diverted under `_workers/` (fewer than 24 rows each) and not published; `logfile.pdf` exists (30 pages, rendered by real Ghostscript 10.02.1); no leftover `motioncorr` process after each run.

Cross-arm identity (6 pairs per config among s0/w1/w2/w4): `identity.compare_trees` identical, and `compare_output_trees.py --products-only` PASS (24 MRC headers+payloads + 24 STAR + joint STAR). Trees were compared as hardlink copies without `_workers/` and with the per-worker output roots and the private `.aggregate-*` staging dir rewritten (they are embedded in per-movie EPS and `.lst`). The merged tree keeps `logfile.pdf.lst` by design (`motioncorr_runner.cpp:1851–1854`, aggregate mode "has always kept it"), so that file is excluded from the copy; this is the only inventory difference to `s0`. Complete (non-PDF) trees still differ in per-movie logs: only `Working on … with N thread(s).`, `Batched patch alignment … free device memory …` and `nvCOMP ingestion: pinned staging pool grown …` lines differ (checked over all 48 log pairs in G and L, `raw/…` JSON `full_different_files`). **Controls that can fail**: an untouched copy of w1 compared with w1 → PASS in both comparators; a copy with one flipped payload byte → FAIL in both. (My first multi-GPU attempt compared a mutated copy to a *different* arm that already failed on path text, which made that control non-discriminating; it is kept as `raw/summaries/multigpu-attempt1-noncomparable/` and not used.)

**Mixed-format 2-worker dataset (coordinator steer 2)**, config L options with `--dose_per_frame 1.0 --eer_grouping 40 --eer_upsampling 1 --ingest auto --ingest_witness`, no gain/`--expected_frames`: 6 movies in STAR order = tutorial 21, tutorial 22, **EMPIAR-10641 `HM70-1_10-A-002`**, tutorial 23, tutorial 24, **EMPIAR-10474 Falcon3 EER**, with three optics groups. w1 (GPU1, j16) vs w2 (GPU1+GPU2, 3+3 movies, j8):

| check | w1 | w2 |
|---|---|---|
| dataset endpoint (`dataset_ready`, aggregate PASS, worker PASS, shards partition input, joint STAR order, `logfile.pdf` 12 pages, no leftovers) | PASS | PASS |
| per-movie products vs the 1-worker run (`identity.compare_trees`, 6 MRC + STAR + EPS) | – | **identical** |
| controls (untouched copy / flipped byte) | PASS / FAIL | |
| `--ingest_witness` | tutorial ×4 `nvcomp`, 10641 `compact`, EER `compact` | same |
| per-movie log markers | 10641: `Staging this movie as native unsigned 8-bit`, `nvCOMP ingestion declined (bits per sample != 16)`; EER: `Staging this movie as native unsigned 16-bit`; tutorial: nvCOMP lines | same |
| retry-triggering movie | 10641: **50/50 patches `converged=no`**, 254 `RMSD` lines = 4 global + 50×5 patch iterations, i.e. the non-converged-patch retry ran for every patch; no `resident retry preparation did not complete` warning, so no fallback-to-download. EER: 8 `converged=no` lines, same pattern. | same |

`compare_output_trees.py` takes one shape per manifest and could not be used on a mixed-shape set; `identity.compare_trees` (shape-agnostic, stricter on headers) was used. The retry path (resident vs download) is not logged explicitly; "resident" is inferred from the absence of the warning at `motioncorr_runner.cpp:3663`. Without the 10641 gain, patch convergence differs from the corpus recipe; the point here is that the retry path is exercised, not scientific accuracy.

## Defects and observations

No defect in `src/`. Items found, with their locations:

1. `tools/profiling/tests/test_import_subset_boundaries.py:24`: hard 30 s subprocess timeout makes `ProfilingKit` load-sensitive (failed once at load ≈27, passed 3 of 3 later). Tooling flake.
2. The brief and #198 name `tools/compare_output_trees.py`; the file is `docs/issue85_laneC/compare_output_trees.py`.
3. `compare_output_trees.py` validates a per-movie inventory of `*.mrc` only, so it cannot compare trees with `_noDW/_EVN/_ODD` products (item 4 used `tools/profiling/lib/identity.py`) or a mixed-shape dataset.
4. The route-record allowance for signed/int8 raw-MRC staging needs the prefix `Released native int` (see item 3); any harness that hard-codes the older four prefixes will flag 10216/10164.
5. Diagnostic only: CPU-vs-CUDA absolute image RMSE / max-pixel gates fail in 9 and 5 of 14 single-movie cases (table above); inheritance shown for 2 of them.

## UNRUN

- Other corpus families (10441, 10641 G/L, 10474-F4) and other movies of each family: one movie per listed family only. EMPIAR-10641 appears only in the mixed multi-GPU dataset.
- Failure/resume/late-writer-fault/report-failure injection through the multi-GPU launcher, and non-prefix resume (docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md plan): not run here; only the endpoint tests in CTest cover them (`MultiGpuScheduling` etc.).
- PDF page **content** equality across arms (only existence, page count and Ghostscript render success were checked); `logfile.pdf` bytes embed run dates.
- `--eer_upsampling 2`/−1, grouping remainder, pinned-route refusal, malformed input, memory-bound controls (W-EER-Q / W-MRC-Q / W-RETRY-Q own those).
- Genuine device poisoning or real OOM (fault injection returns a status code only).
- SCARF / any second venue; timing, scaling and peak-VRAM claims; science (CTF/FSC) equivalence; gain orientation correctness; THP variations.
- GPU-silicon witness for the 42 first-pass campaign GPU runs (only the pin; 3 re-witnessed).

## Reproduce

`tools/` holds the scripts as run (`qual_lib.py` shared helpers, `run_ctest.sh`, `product_campaign.py`, `fallback178.py`, `fallback178_injected.py`, `multigpu_step.sh` + `multigpu_publication.py`, `inherited_control.py`, `gpu_witness_check.py`, `make_tables.py`, `summarize_ctest.py`). Paths are the 4GPUs scratch `/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/`. Bulk MRC/PDF outputs were deleted after grading; whole-file MRC SHA-256 values are in the JSON summaries. Raw data: `raw/summaries/*.json` (per case: argv, binary sha256, cpu mask, env, rc, wall, RSS, route witness, lock waits, comparator outputs), `raw/ctest/`, `raw/logs/` (build and driver logs), `raw/*-run-logs/` (per-run stdout, `time -v`, comparator JSON).
