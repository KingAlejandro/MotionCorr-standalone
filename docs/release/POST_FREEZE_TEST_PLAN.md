# Post-freeze validation plan (DRAFT)

Status: **draft, revision 1** (after the R-REL accuracy review of PR #201). This is the heavy validation campaign that runs **after** the RC0 freeze, on the frozen SHA. It is a plan:
every row is **UNRUN** and every result cell is **pending**. Resource lanes, locks and venues are those recorded on
[#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198) (checked 2026-10-16 19:21Z) and must be re-checked
at run time (`AGENTS.md`: check occupancy before running work; leave unrelated processes alone; record actual resources).

The freeze-time gate is `RELEASE_CHECKLIST.md` (QF). This plan adds breadth, soak and scientific evidence that QF does not
cover. Nothing here changes a gate or tolerance (`docs/gate_contract.md`).

## 1. Venues

| Venue | Hardware (as recorded on #198 / in the #186 evidence) | Use in this plan | Constraints to re-check |
|---|---|---|---|
| 4GPUs | 4 x A100 80 GB, 124 CPUs; GPU idle state and `/tmp/motioncorr-*.lock` per run; `/home` was 100 % full on 2026-10-16 | native CUDA correctness, nvCOMP, multi-GPU 1/2/4, failure injection | take the per-GPU and `bench` locks; scratch outside `/home` (the RC0 lane used `/mnt/clathrin/alex-motioncorr-rc0`, at most 300 GB) and bounded `/dev/shm`; THP is `madvise` there (#186) |
| SCARF | reachable; GPU queue and group limits; CPU partition for prebuilds | second venue for QF-level product checks and dataset-ready timings | THP is `always` there, so absolute times are not comparable with 4GPUs or cpu64 (`docs/workload_corpus/cpu/README.md`) |
| cpu64 | AMD EPYC 7763, 64 cores, SMT off, 2 NUMA nodes, 226 GB RAM; `motioncorr-cpu64-bench.lock` | CPU-only corpus, thread scaling, CPU soak | one benchmark holds the lock at a time (`docs/workload_corpus/cpu/README.md`); no competing CPU performance campaign |

Timings are comparable only under matching conditions (same venue, allocation, THP setting, binary, inputs and storage).
Never combine venues or multiply single-GPU gains.

## 2. Corpus families

The ten families of `docs/workload_corpus/families.json` (hashes in `corpus.md`; 21 GB on disk): tutorial (16-bit Deflate TIFF, one row per strip),
EMPIAR-10028 (float32 MRC), 10361/10641/10441 (LZW BigTIFF), 10474 Falcon 3 and Falcon 4 (EER), 12963 (EER with gain), 10164
(MRC mode 0, read as signed int8; tilt series), 10216 (mode 1 MRC). Run each with the family's gain and EER options, configs G (global only) and L
(`--patch_x 5 --patch_y 5`). Distinct versus replayed inputs are labelled separately (as in #186). The corpus document still carries
two stale labels (tutorial "u8", EMPIAR-10164 "u8"); `SUPPORT.md` §2 gives the corrected description and the coordinator is
fixing the corpus text separately.

Add what the corpus lacks, as separate small rows: compressed MRC (needs `pbzip2`/`xz`/`zstd`), signed TIFF, float TIFF, 4-bit
inputs, a multi-optics STAR, a tomography STAR, and a movie that triggers patch non-convergence (EMPIAR-10641 and 10216 do).

## 3. Option matrix

Per family where the option applies. Two kinds of comparison, never interchanged:

- **Cross-backend:** each CUDA arm against the CPU arm **with the same options**, per movie, with
  `tools/compare_motioncorr.py --gate backend` and its required GNU `time -v` log. The 0.001 relative-RMSE figure is a
  non-blocking diagnostic there (`docs/gate_contract.md`). Strict tree identity is not used across backends.
- **Same-backend invariance** (routes, repeats, worker counts, resume): `docs/issue85_laneC/compare_output_trees.py`, exact.
- **Option on versus off is not an equality test.** Binning, frame selection, grouping, dose weighting and defect handling change
  products by design. Each option arm needs a **named invariant** (for example `--save_noDW` leaves the dose-weighted `.mrc`
  unchanged, `--even_odd_split` leaves the main `.mrc` unchanged) plus complete products, expected geometry and sampling.

Options:

- patches: none, 3 x 3, 5 x 5 (a value of 2 is skipped by the program, `src/motioncorr_runner.cpp:308-314`);
- dose weighting off/on (voltage must be within 2 kV of 100, 200 or 300), `--save_noDW` (only produces a separate file with dose weighting), `--even_odd_split`, `--grouping_for_ps` with `--ps_size`, `--float16`;
- `--bin_factor` 1, 2 and a non-integer value (binned dimensions must be even); early binning on and `--no_early_binning` (on CUDA, early binning prevents the
  resident session, `:2264`);
- `--group_frames`, `--first_frame_sum`/`--last_frame_sum`, `--max_iter`;
- gain with `--gain_rot` 0-3 and `--gain_flip` 0-2; defect text file and defect map; `--skip_defect`; `--seed`;
- EER grouping and upsampling -1, 1, 2 (and 3 on 4096 x 4096 only; 2048 x 2048 and 2-bit sub-pixel EER take only 1 and 2), including a
  value that crosses the uint16 limit and, on an 80 GB card, upsampling 2 on a large EER movie (about 75 GiB estimated, never run);
- `--ingest auto|nvcomp|compact|float` with `--ingest_witness` on every run; pinned-route refusals on ineligible movies;
- `--j` 1, 4, 8; `--max_io_threads`; `--sync_output`.

Record the route witness for every CUDA run. A row without a witness is not a route claim.

## 4. Failure injection

Reuse existing controls and add native runs on the frozen SHA:

- write faults and late-writer faults (`WriteFaults*`, `OutputStageFaults`, `ImageWriteFaults`; `docs/issue99_write_faults/`);
- damaged and truncated movies (`DamagedMovie`), wrong frame count (`--expected_frames`), gain size mismatch, SerialEM defect file;
- CUDA: injected allocation, upload and nvCOMP failures (`CudaFaultMatrix`, `CudaPreprocessingFailurePaths`,
  `CudaNvcompAcceptanceFailures`; `CudaU16FailurePaths` exists only when configured with `-DMOTIONCORR_U16_TEST_MOVIE=<uint16 TIFF>`,
  `CMakeLists.txt:760-779`, and a test that was not registered is not an executed pass) plus the **native** CUDA-to-CPU unweighted fallback, which is UNRUN
  (#198 item C1), and the resident patch retry under injected failure (#197);
- multi-GPU: owned-worker failure with a TERM-ignoring descendant, late writer fault, report failure, and a non-prefix resume
  (`docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`);
- `logfile.pdf` render failure in normal and `--aggregate_only` modes (`SUPPORT.md` §6, depends on fix F1);
- `_PS.mrc` left behind by a movie that fails after the power spectrum is written (`SUPPORT.md` §6).

Each negative needs a healthy positive control that proves the intended route with `--ingest_witness`; a pinned-route refusal writes no
witness line of its own, and a witness line is a route-selection record, not a completion record (`SUPPORT.md` §2). Required
outcome: named failure, no completion STAR for the failed movie, healthy movies' per-movie products retained, **no joint output for the
batch**, no owned process left. The program does not roll back: a failed movie may leave a truncated or earlier per-movie file
and `_PS.mrc` (`SUPPORT.md` §6, `tests/test_write_faults.py:21-30`); record what is on disk and do not assert its absence. The distinction between component injected faults
and a genuinely poisoned device must stay explicit in the report. Malformed-input behaviour of the nvCOMP decoder is bounded
by D1/#134 and is not a safety claim.

## 5. Soak and long queues

- A long single-process queue per backend (hundreds of movies, repeated tutorial entries are labelled as replayed input):
  RSS and VRAM trends, descriptor and pinned-memory counts, product count and a periodic product-hash check.
- Memory growth across movies with the frame buffer pool and device gain retention (`docs/host_buffer_reuse.md`,
  `CudaDeviceGainPool`, `CudaGeometryRetention`).
- Multi-GPU dataset runs at 96 movies and above (prior 96-movie evidence: `docs/multi_gpu/scaling/README.md`), with the aggregate
  phase timed separately because it does not scale (about 31 s at 96 movies in that evidence).
- Interrupted and restarted runs under unchanged settings. Resume under changed settings is a known limitation (#149), so soak
  restarts must use fresh output directories for any setting change.

Acceptance is product identity and stable resources over the queue, not speed.

## 6. Multi-GPU 1/2/4

Process-per-device only, through `tools/multi_gpu/run_dataset.py`. Use at least five balanced, interleaved blocks per count
with a fixed total CPU budget (`--cpu-budget`), the same options, cache and storage, and the full output set. Record total
dataset-ready wall plus the worker and aggregate phases, summed RSS or PSS and UUID-filtered VRAM traces, and the per-worker
device witness. Native identity with a single-process run is required before any timing is quoted. Real distinct inputs
(EMPIAR-10361) and replayed tutorial entries answer different questions; label them. SCARF dataset-ready numbers stay separate from
4GPUs and from direct-process runs. Reference: `docs/multi_gpu/scaling/README.md` (source `d7339fd`, not RC0).

## 7. Scientific validation links

- [#61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61): scientific non-inferiority of CPU, CUDA and hybrid motion
  correction (Tier D: downstream CTF/FSC/B-factor).
- [#73](https://github.com/KingAlejandro/MotionCorr-standalone/issues/73): native CUDA scientific outcomes on an independent
  collection.
- [#36](https://github.com/KingAlejandro/MotionCorr-standalone/issues/36): CUDA relative-RMSE divergence (0.002899-0.010082 versus 0.001).
- Downstream substrate and caveats are recorded in `docs/gate_contract.md` §4A.5, §8. Neither the existing absolute bounds nor the backend
  profile establish scientific equivalence on unseen collections.

Until #61 and #73 report, RC0 makes no scientific claim beyond Tiers A to C, and the release notes must say so.

## 8. Resource requirements

From the #186 evidence at main `116eb04a` (not the frozen SHA; re-measure at freeze):

- CPU, cpu64, `--j 1/4/8`: peak RSS 2.2 GiB (EMPIAR-10028) to 36-39 GiB (EMPIAR-10441, 11520 x 8184 x 50); 21 GiB for the 144-frame
  Falcon 4 EER at `--j 1` (`docs/workload_corpus/cpu/README.md`). The most demanding CPU row takes about 553 s (`--j 1`, config L)
  per movie.
- GPU, one A100: VRAM peak 2.7 GiB (10028) to 39.3 GiB (10441); host RSS 0.4-12 GiB; fixed cost per process 0.53-1.25 s
  (`docs/workload_corpus/gpu/README.md`).
- Estimated frames that fit a 24, 40 or 48 GiB card are in that README's VRAM table; those are arithmetic from the 80 GB measurement, not
  runs on small cards.
- Per-geometry VRAM floor: two float-size resident stacks (about `2 x frames x nx x ny x 4` bytes) plus 0.7-4.2 GiB; EMPIAR-10441 peaked at
  39.3 GiB. Behaviour when the session cannot be allocated (streaming fallback or a clean failure) is **not qualified**; register item
  QM on #198 is pending and the forced-OOM control belongs to this campaign if QM is not closed before freeze.
- Host RAM: `--grouping_for_ps` on the resident CUDA path downloads the full Fourier movie to the host (`src/motioncorr_runner.cpp:3205-3212`),
  about one extra float-movie-sized allocation; include it in any RAM budget for that option.
- EER upsampling 2 quadruples movie storage (about 75 GiB estimated for 144 groups, not run).
- Disk: 21 GB corpus, plus scratch for products (a 300 GB cap was set for the RC0 pre-freeze programme on #198).
- Wall: the #186 GPU pass held locks for 63.2 min over 90 blocks; the CPU pass needed about 8.6 h of run time plus settle waits and
  extrapolated to roughly 12.5 h of lock time for `--j 4`, so `--j 4` was dropped for the two largest families.

## 9. Bug-fix-only policy after freeze

After the freeze SHA is set:

1. **Only defect fixes enter.** No feature, optimisation, new route, dependency or tolerance change. Parked and no-go experiments
   (#198 register: C8, C9, L1, E2, T1) stay out unless the maintainer reopens scope.
2. A fix needs a linked issue stating the defect, a discriminating test that **fails without the fix**, and a minimal diff.
   Preserve numerical results, metadata and failure/publication behaviour unless the defect is exactly that; an intentional
   output difference is explained and needs maintainer sign-off (`AGENTS.md`). A fix for upstream-inherited behaviour changes
   parity with `ad0b230c` and needs the same sign-off.
3. Merge to `main` only after independent review, current-head CI and the native evidence the claim needs (D3). Never relax a gate
   to make a fix pass.
4. **Re-entry into qualification.** Each fix produces a new candidate SHA. Classify its reach:
   - docs or tests only: rerun the affected tests; no QF rerun;
   - CPU-only source: CPU build, full CPU CTest, Tier A, known-motion CPU, and the format rows its code touches;
   - CUDA or shared source: full CTest on all three configurations, the checklist rows whose route the change touches, and native
     execution on a GPU. A CUDA fix is never qualified by compilation alone;
   - publication, report or multi-GPU tooling: the dataset endpoint rows and failure injection.
   Rows not rerun keep their earlier SHA in the report and are labelled as not retested on the new SHA; they are not relabelled as passes
   of it.
5. Update `RC0_ACCEPTANCE_REPORT.md` with the new SHA, what was rerun, what was not, and any change to supported configurations
   or known limitations. A new tag is a maintainer decision (D4).
6. A defect that cannot be fixed within scope is documented as a known limitation in `SUPPORT.md` instead.
