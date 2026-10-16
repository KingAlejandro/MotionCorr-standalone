# Post-freeze validation plan (DRAFT)

Status: **draft, revision 3, stays DRAFT until the freeze** (after R-REL round 2, R-REL-B and the R-QA2 audits of PR #201, and the maintainer decisions D1, D2, T3, D5, D6, D7). RC0 is an **evaluation** release, not a stable one (D7). This is the heavy validation campaign that runs **after** the RC0 freeze, on the frozen SHA. It is a plan:
every row is **UNRUN** and every result cell is **pending**. Resource lanes, locks and venues are those recorded on
[#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198) (checked 2026-10-16 19:21Z) and must be re-checked
at run time (`AGENTS.md`: check occupancy before running work; leave unrelated processes alone; record actual resources).

The freeze-time gate is `RELEASE_CHECKLIST.md` (QF). This plan adds breadth, soak and scientific evidence that QF does not
cover. Nothing here changes a gate or tolerance (`docs/gate_contract.md`).

## 0. Priority 1: S1, CPU versus CUDA local alignment (PROVISIONAL)

S1 is the first item of this campaign and has priority over every other row. The statement that RC0 ships is in `SUPPORT.md` §0 and `README.md`
(maintainer decision D7); evidence: [PR #212](https://github.com/KingAlejandro/MotionCorr-standalone/pull/212) (diagnosis) and
[PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209) (backend diagnostic table, main `1db86902`: relative RMSE CPU versus CUDA 0.43-0.60
on EMPIAR-10216, 10474 Falcon 3 and 12963 with 5 x 5 patches). The campaign, in this order:

1. **More movies per family.** Run CPU and CUDA local alignment (configs L and 3 x 3) on many more distinct movies of every #186 family, not one
   or two, and record per movie: the backend gate result, the number of patches that converge on each backend, the patch sets that differ, and the
   relative RMSE. Establish how often S1 occurs and on which families (it was seen on families with non-converging patches; the tutorial, 10361,
   10164 and 10028 were 0.0013-0.014).
2. **Older builds.** Re-run on older builds to establish longevity. S1 is already present at `116eb04a`; test earlier builds too, and a
   CPU build against CPU builds (CPU-versus-CPU is the control).
3. **CCF near-tie logging.** Log the cross-correlation peaks (top two values and positions, and their ordering on each backend) at every frame of
   the patches whose trajectories diverge, to test the diagnosed mechanism: two peaks within a few float ulps ordered differently by the two backends.
   PR #212's finding that using the CPU tie rule (#70) changed two outputs slightly but did not explain S1 stays the reference result; whether the
   small map differences are pure rounding is open, and other CUDA defects are not excluded.
4. **Downstream scientific comparison.** CTF, FSC and relative B-factor on CPU-aligned versus CUDA-aligned micrographs of the same movies (#61, #73),
   including at least one S1 family. Only this can say whether the difference matters.
5. Keep thresholds unchanged. Any change to a gate or default is a separate maintainer decision (D7 options 2 and 3 are post-RC0).

Execution table. Owners are **roles to be assigned by the coordinator when the campaign starts** (no post-freeze owner exists yet); venues and locks are
those of section 1 and must be re-checked at run time.

| Step | Task | Venue and lock | Owner / role | Completion / acceptance criterion |
|---|---|---|---|---|
| S1.1 | Multi-movie sweep of configs L and 3 x 3 over all ten #186 families | 4GPUs (per-GPU correctness lock) for CUDA arms; cpu64 (`motioncorr-cpu64-bench.lock`) for CPU arms | qualification worker | per-movie table committed with the `--gate backend` metrics, converged patch counts per backend, differing patch sets and relative RMSE; S1 incidence stated per family |
| S1.2 | Longevity: builds older than `116eb04a`, plus a CPU-versus-CPU control | 4GPUs / cpu64 | qualification worker | commit range over which S1 is present recorded; the CPU-versus-CPU control is identical (otherwise the sweep is invalid) |
| S1.3 | CCF near-tie logging on the divergent patches (top two peaks, values and positions, per backend) | 4GPUs, one GPU lane (diagnostic build kept outside the RC0 source) | diagnostic worker | per-frame peak-separation records for every divergent patch; the near-tie mechanism confirmed or refuted; whether the small map differences are pure rounding stated as established or still open |
| S1.4 | Downstream CTF, FSC and relative B-factor, CPU-aligned versus CUDA-aligned (#61, #73), including at least one S1 family | 4GPUs / SCARF with a RELION downstream pipeline | science validation owner and maintainer | comparison report posted on #61 and #73; the maintainer then confirms or changes the D7 support class in `SUPPORT.md` |

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
(`--patch_x 5 --patch_y 5`). Distinct versus replayed inputs are labelled separately (as in #186). `docs/workload_corpus/corpus.md` and `families.json` carry the
corrected labels for the tutorial (16-bit Adobe-Deflate TIFF, RowsPerStrip 1, 3710 x 3838) and EMPIAR-10164 (MRC mode 0, read as signed int8);
the historical #186 baseline results under `docs/workload_corpus/{cpu,gpu}/` keep their recorded wording except for the corrected dimension order and format labels.

Add what the corpus lacks, as separate small rows: compressed MRC (needs `pbzip2`/`xz`/`zstd`; **run `xz -t`, `zstd -t` or `bzip2 -t`/`pbzip2 -t` on every input first**, F4), signed TIFF, float TIFF, 4-bit
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
  resident session, `:2269`);
- `--group_frames`, `--first_frame_sum`/`--last_frame_sum`, `--max_iter`;
- gain with `--gain_rot` 0-3 and `--gain_flip` 0-2; defect text file and defect map; `--skip_defect`; `--seed`;
- EER grouping and upsampling -1, 1, 2 (and 3 on 4096 x 4096 only; 2048 x 2048 and 2-bit sub-pixel EER take only 1 and 2), including a
  value that crosses the uint16 limit and, on an 80 GB card, upsampling 2 on a large EER movie (one run per arm sampled 79,522 MiB NVML process VRAM on an 81,920 MiB card, PR #208, little observed headroom; repeat for variability);
- `--ingest auto|nvcomp|compact|float` with `--ingest_witness` on every run; pinned-route refusals on ineligible movies;
- `--j` 1, 4, 8; `--max_io_threads`; `--sync_output`.

Record the route witness for every CUDA run. A row without a witness is not a route claim.

## 3a. RELION 5.1 compatibility rows (#216)

From [#216](https://github.com/KingAlejandro/MotionCorr-standalone/issues/216); summary in `SUPPORT.md` §0a. All **UNRUN**.

| Row | What to test | Venue and owner | Acceptance / decision criterion | Inputs |
|---|---|---|---|---|
| (a) EER frame-count metadata | The per-movie STAR counts `rlnNrOfFrames` / `rlnTomoTiltMovieFrameCount` (and `--expected_frames`) are compared with the **decoded grouped** frame count, which for EER is `fractions / --eer_grouping` with the trailing remainder dropped (`src/motioncorr_runner.cpp:454-478, 2141-2146, 2125-2127`). Run EER movies whose STAR records the **raw fraction count** and ones that record the grouped count; include a **RELION 5 tomography STAR** | cpu64 or 4GPUs (one lane, correctness lock); qualification worker | the matrix (raw-fraction STAR versus grouped-count STAR) x (`--eer_grouping`) of outcomes recorded with exact error text and exit status, and RELION 5.1's behaviour on the same STARs; if a raw-fraction RELION 5 tomography STAR fails, update #216 with the reproduction and the maintainer decides whether to reconcile or to document it in `SUPPORT.md` §0a | e10474f3/f4, e12963; a RELION 5 tomography import of EER tilts |
| (b) pipeliner and GUI with no `logfile.pdf` | Run RELION 5.1's pipeliner/GUI job type for motion correction with the standalone as the executable, once with Ghostscript (full `logfile.pdf`) and once without or with a forced failed render (no `logfile.pdf` after F1). Compare with RELION's own end state without Ghostscript | a host with RELION 5.1 and its pipeliner/GUI installed; release-docs owner and maintainer | pipeliner job status (succeeded, or a missing-node error) recorded with and without `logfile.pdf`, and RELION's own end state without Ghostscript; `SUPPORT.md` §0a updated to say whether a missing `logfile.pdf` breaks a pipeliner job | tutorial subset |
| (c) RELION 5.1 versus standalone CPU on the #186 families | Extend `docs/spa_24_movies_validation.md` (24 tutorial movies, exact profile, `--j 1` and `--j 4`; 1/24 exact at `--j 1`, #20) to the ten #186 families: same options per family (the defect-replacement random sequence is the open parity question, #20, so record whether movies share a process), pixel and STAR comparison with the exact and relaxed profiles reported **separately** (upstream parity is a separate axis, `docs/gate_contract.md` §1) | cpu64 under `motioncorr-cpu64-bench.lock`; qualification worker | ten-family exact and relaxed comparison tables published as an extension of `docs/spa_24_movies_validation.md`, with whether movies share a RELION process documented; no tolerance relaxed | all ten families in `docs/workload_corpus/families.json` |

Row (c) needs a CPU-only build of full RELION 5.1 at `ad0b230c` on the same inputs and a venue booked for it; record both binaries' hashes, resources, inputs
and options as in `RC0_ACCEPTANCE_REPORT.md` §6.

## 4. Failure injection

Four kinds of case, with different pass criteria. Do not apply one rule to all of them: the program preserves some inherited acceptance of damaged
input by decision (D5 for compressed MRC, D6 for EER), and a case that is expected to publish is characterised, not rejected.

Common to every case: a healthy positive control that proves the intended route with `--ingest_witness` (a witness line is a route-selection
record, not a completion record, and a pinned-route refusal writes none, `SUPPORT.md` §2); the full on-disk inventory is recorded, because the
program does not roll back (`SUPPORT.md` §6, `tests/test_write_faults.py:21-30`): a failed movie may leave a truncated or earlier per-movie
file and `_PS.mrc`, so absence is never asserted.

### 4.1 Rejection controls: must fail

Expected for every row: run exit status 1 (a nonzero exit, not a crash or signal); a named failure on stderr; **no completion STAR** for the failed movie;
**no joint output** (`corrected_micrographs.star`, `logfile.pdf`) for the batch; healthy movies' per-movie products retained and byte-identical to their
standalone runs (`src/motioncorr_runner.cpp:1083-1089`).

| Control | Input | Evidence or baseline |
|---|---|---|
| Wrong grouped frame count | EER (or any movie) with `--expected_frames` or a STAR count different from the decoded count; for EER the count is `floor(fractions / eer_grouping)` | #208 b1: exit 1, "frame count mismatch: expected 58 frames, but decoded 34 frames", no MRC/STAR for it, movies 1 and 3 complete, no joint STAR |
| Wrong gain | gain reference of the wrong size (including a 4K gain with `--eer_upsampling -1`) | #208 b6, c17: exit 1, both movies fail, "Unsupported gain size", no MRC/STAR; `src/motioncorr_runner.cpp:2210-2218` |
| Pinned route cannot be honoured | `--ingest nvcomp` or `--ingest compact` on an ineligible movie; EER overflow with pinned compact | #208 overflow controls and #204: exit 1, no MRC/STAR for the movie, no witness line |
| Unsupported MRC mode, SerialEM defect text, malformed TIFF | MRC modes 3/4; a SerialEM-format `.txt`; `DamagedMovie` fixtures | refused at read or initialise (`src/rwMRC.h:209-228`, `src/motioncorr_runner.cpp:267-272`; `DamagedMovie` test) |
| Truncated raw MRC movie, gain reference, defect map | truncated copies, every mode | **after [PR #205](https://github.com/KingAlejandro/MotionCorr-standalone/pull/205) merges only** (F3/F3b): must fail as above. **Before #205 this is not a rejection control**: today it publishes (listed in 4.2 as a baseline) |
| Injected fatal CUDA error | `CudaResidentRetryFailures`, `CudaFaultMatrix`, `CudaPreprocessingFailurePaths` (error codes injected, not a poisoned device) | #207: exit 1, refusal, no publication, the later movie refused at session initialisation |
| Write faults, late writer fault, report failure; multi-GPU owned-worker failure | `WriteFaults*`, `OutputStageFaults`, `ImageWriteFaults`; `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md` | named failure, no dataset-ready success, retained healthy movies, no owned process left |
| `logfile.pdf` render failure | forced failed render | normal mode: exit 0, **no `logfile.pdf`** left (F1, #200); `--aggregate_only`: strict failure, no joint STAR (`SUPPORT.md` §6) |

### 4.2 Characterisation: expected to publish (inherited behaviour kept by decision)

The expected outcome is the **published** outcome. Record it exactly; the pass criterion is that it matches the decided behaviour, and the report states
that the input was accepted. These are not rejection tests, and applying 4.1 to them would contradict D5 and D6.

| Case | Input | Expected exit and publication | Decision and evidence |
|---|---|---|---|
| EER fraction with a wrong decoded pixel count | one fraction's strip set to 0xFF or 0x00 | exit 0; WARNING on stderr "The number of pixels is not right ... This frame is skipped."; the movie **publishes** with a different product; joint STAR lists it | D6; #208 b3, b4; `src/renderEER.cpp:564-567` |
| EER corruption that keeps the pixel count | 4096 random bytes inside one fraction's strip | exit 0, **no warning**, movie publishes with a different product | D6; #208 b2 |
| Truncated EER without an expected count | file cut at 60 %, no `--expected_frames`, no STAR count | exit 0, a shorter movie (34 groups instead of 58) **publishes silently** | D6; #208 b5 |
| Shortened EER with an unchanged grouped count | trailing fractions removed so `floor(fractions / eer_grouping)` is unchanged (for example 2331 to 2330 fractions at grouping 40) with the correct `--expected_frames` | exit 0, publishes; **the count check cannot see it** | `src/motioncorr_runner.cpp:2125-2127, 2141-2146` |
| Compressed-MRC end-of-stream corruption | `.xz` with the last byte removed, a corrupt index CRC, a non-zero decoder exit after a full stream | exit 0, movie **publishes** (the decoder exit status is not checked); a short read in mid-stream is still caught and fails. **The independent validator must reject the file first**: `xz -t`, `zstd -t`, `bzip2 -t`/`pbzip2 -t` exit non-zero, and the run is then not started | D5/F4 (fix #214); #204 damage records; `src/image.h:1939-1953` |
| `_PS.mrc` left behind | `--grouping_for_ps` with a patch-alignment failure of the same movie | the movie fails (exit 1, no completion STAR, joint outputs withheld) but `<movie>_PS.mrc` **remains** on disk; record it, do not assert absence | `src/motioncorr_runner.cpp:3309` (inherited; `SUPPORT.md` §6 item 1) |
| Truncated raw MRC before #205 | truncated movie, gain or defect map, current `2b3c74b3` | exit 0, products and completion STAR **publish** from partly unread memory (float and compact routes publish different unread bytes) | #198 register F3/F3b; baseline only |
| Big-endian mode-0 MRC with nx = 128 (F5) | such a file | observed on the tested GCC build: fails identically on every tested route; record the exit status and message. **No portable clean failure is promised** (`abs(INT_MIN)`, `src/rwMRC.h:149`) | D5; #204 |
| Malformed EER decoder input (EER-MS) | malformed streams | **do not run on production lanes.** Only under an address sanitizer in an authorised scratch lane; record the outcome, assert nothing. Memory safety is not established (`src/renderEER.cpp:416-555`) | #198 register EER-MS; R-QA2 on #208 |
| nvCOMP corrupt Deflate body | corrupt or growing TIFF on a `USE_NVCOMP=ON` build | not a safety claim (D1): the route assumes complete, unmodified files; characterise only, in an authorised lane, and use `--ingest compact` for unverified files | D1; #134; #215 |

### 4.3 Recovery controls: must complete

Injected recoverable CUDA failure: exit 0, one WARNING, products identical to the unfaulted run (#207: identical; #209: one injected recoverable
CUDA-to-CPU fallback under `--gpu`, identical to `d7171b81`). The six CPU-backend checks of CUDA-linked binaries without `--gpu` are a separate control.
Re-verify both on the frozen SHA. Neither is real out-of-memory or device-poisoning evidence.

### 4.4 Controls that already exist, and what they do not cover

- CUDA tests: `CudaFaultMatrix`, `CudaPreprocessingFailurePaths`, `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`, `CudaResidentRetryFailures`;
  `CudaU16FailurePaths` exists only when configured with `-DMOTIONCORR_U16_TEST_MOVIE=<uint16 TIFF>` (`CMakeLists.txt:788-807`), and a test that was not
  registered is not an executed pass.
- All fatal-path CUDA tests inject error codes; a **genuine device-poisoning** control is post-RC0 (TST2,
  [#213](https://github.com/KingAlejandro/MotionCorr-standalone/issues/213)). Real out-of-memory and the QM forced-OOM control are UNRUN.
- Malformed-input behaviour of the nvCOMP decoder is bounded by D1/#134 and of the EER decoder by EER-MS; neither is a safety claim.

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
- Host RAM: `--grouping_for_ps` on the resident CUDA path downloads the full Fourier movie to the host (`src/motioncorr_runner.cpp:3210-3217`),
  about one extra float-movie-sized allocation; include it in any RAM budget for that option.
- EER upsampling 2 quadruples movie storage: a 144-group Falcon 4 movie completed at 79,522 MiB sampled NVML process VRAM on an 81,920 MiB card (calculated 80,520 MiB; about 2.3 GiB remained), host RSS 21,547 MiB compact versus 40,171 MiB float (single runs, PR #208). A sample, not an upper bound or guaranteed fit; little observed headroom on 80 GB.
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
