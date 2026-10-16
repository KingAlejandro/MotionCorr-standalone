# RC0 acceptance report (SKELETON, partly filled)

> **EVALUATION RC0, not a stable release** (maintainer decision D7, [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198)). No
> unrestricted or stable support is claimed for CUDA local alignment (known limitation **S1**, PROVISIONAL), and no scientific equivalence or
> preference for either backend is established.

Status: **skeleton, revision 2.** Filled from the qualification PRs #209 (Q1), #204 (raw MRC), #208 (EER), #207 (resident retry) and #212 (S1), all at
main `1db86902` and reported on #198. The frozen SHA and the QF rows stay **pending freeze**. A planned or unrun check is **UNRUN**, never PASS.
Evidence cited here comes from those PRs and #198 and was not re-run by the author of this report; the PRs are open, so their claims are as reported
there. Rows labelled "reference" come from earlier evidence at an older SHA and are not RC0 results.

## 1. Frozen SHA

| Field | Value |
|---|---|
| Frozen source SHA | **pending freeze** (decision D4 on #198) |
| Base for this draft | main `2b3c74b3` (= `1db86902` + #200 F1 + #210 TST1); qualification evidence is at `1db86902` |
| Register items merged | C1 #178, C2 #187, C3 #188, C4 #185 (`d7171b81`), E1 #196 (`4b849165`), M1 #195 (`faf5fbdf`), R1 #197 (`0ac2726a`), F1 #200 (`ea86fc90`), TST1 #210 (`2b3c74b3`); merge SHAs of C1-C3 are in the #198 register |
| Pending, not merged | **F3/F3b** [PR #205](https://github.com/KingAlejandro/MotionCorr-standalone/pull/205) (truncated raw MRC, gain, defect map fail explicitly; D5 approved, in qualification); **T3** checked-arithmetic hardening of the nvCOMP pre-decode arithmetic (approved for RC0, `fix/rc0-nvcomp-checked-arithmetic`); **QM** memory admission on smaller GPUs (no worker assigned) |
| Bounded experiments, not in RC0 unless they pass the amended rule | C5 #179, C6 #181, C7 #183 ([#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6223528151)); E2 #193 option 2 |
| Excluded | T1 #138 (NO-GO for RC0, parked [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206)); L1 #141/#152 nvTIFF (NO-GO, not used); C8 #184 and C9 #177/#182 (NO-GO); #149 deferred; TST2 genuine device poisoning (post-RC0, #213); #214 (compressed-MRC exit status), #215 (nvCOMP file identity) post-RC0 |
| CI run on the frozen head | pending freeze |
| Decisions recorded | D1: option 1, documented trusted-input precondition (no code change); D2: interim policy A (optional, default-off, not vendored, no project-distributed linked binaries); T3: checked-arithmetic hardening for RC0; D5: F3/F3b fail-closed approved, F4 a documented limitation; D6: preserve the EER skip-and-warn recovery; D7: evaluation RC0 with S1 provisional. D3 (each merge) is per PR; D4 (scope and SHA) is open |

## 2. Supported and unsupported configurations

Classes follow `SUPPORT.md` §1; evidence is at `1db86902` unless stated. "QF" = re-verification on the frozen SHA, **pending freeze** for every row.

| Configuration | Class | Evidence at `1db86902` | QF |
|---|---|---|---|
| CPU `--use_own`, Release, Linux x86_64 | supported (intended) | CPU CTest 58/59 (`ProfilingKit` 30 s load timeout, passed on rerun); CPU build route-invariance runs 14/14 exit 0 (#209) | pending freeze |
| CPU `--use_own`, Release, macOS arm64 | supported (intended) | local author run at the merge head `67b5315b`: 60 collected, 57 passed, 2 failed (`SyntheticRegression`, `MultiGpuScheduling`, both inherited), 1 skipped (`RELEASE_CHECKLIST.md` §3) | pending freeze |
| CUDA, one device, no nvCOMP | supported for evaluation; **local alignment: S1, no unrestricted claim** | CTest 89/89, 0 skipped (#209); route invariance auto vs float 14/14 identical on 7 families x G/L; #178 CPU unweighted path executed natively 6/6 identical to pre-#178 | pending freeze |
| CUDA, one device, nvCOMP (`USE_NVCOMP=ON`) | experimental; trusted-input precondition (D1) | CTest 92/92, 0 skipped (#209); tutorial route `nvcomp`, identical to float | pending freeze |
| Multi-GPU via `run_dataset.py` | supported for evaluation | 1/2/4 workers x 24 tutorial movies, G and L, 6/6 endpoint PASS, distinct witnessed UUIDs, identical to a single process, real-Ghostscript 30-page `logfile.pdf`; mixed tutorial + 10641 + EER 2-worker run identical to 1-worker (#209) | pending freeze |
| Raw integer MRC modes 0/1/6 (compact route, #195) | supported on valid input | real 10164/10216/10028 G and L, auto vs float 6/6 identical; synthetic modes 0/1/6/2/12/101 28/28; compressed xz/zstd 16/16 on the float route; pinned-compact refusals 15/15; modes 3/4 refuse (#204, evidence audit corrected @ `5944617b`) | pending freeze |
| Truncated raw MRC, gain, defect map | **today: products published from partly unread memory** (F3); fails explicitly only with PR #205 | #204, #198 register F3/F3b | pending #205 |
| Compressed MRC (`.bz2`/`.xz`/`.zst`) | supported on valid, **independently validated** input (F4: decoder exit status unchecked) | #204 (native `pbzip2` UNRUN; `.bz2` tested through a `bzip2 -cd` shim) | pending freeze |
| EER compact route (#196) | supported on valid input; `--expected_frames` recommended (D6) | 34/34 strict tree identities (31 CUDA auto vs float incl. upsampling -1/1/2/3, gain, defect file, synthetic 65000/65002; 3 CPU old vs new); all seven corpus EER files are encoding 65001 at 4096 x 4096; 65000/65002/2K synthetic only (#208) | pending freeze |
| Resident patch retry (#197) | supported | success path 10641 41/50 and 10216 30/50 patches retried, identical to pre-#197 and to `1db86902` with #197 reverted (28 comparisons); injected recoverable failure identical, injected fatal failure refuses with no publication; 1- vs 2-worker identical (#207) | pending freeze |
| **CUDA local alignment vs CPU** | **S1, PROVISIONAL**: relative RMSE 0.43-0.60 on 10216, 10474 Falcon 3, 12963 (5 x 5 patches) | #209 backend diagnostic, #212 diagnosis | heavy testing is the priority after freeze |
| Input rows R1-R12 | per `RELEASE_CHECKLIST.md` §7 | partly covered by #204, #208, #209 | pending freeze |
| Unsupported (named in `SUPPORT.md` §1) | unsupported | n/a | n/a |

## 3. Known limitations

Carry over from `SUPPORT.md` §0, §5, §6 and §8, updated at freeze:

- **S1 (PROVISIONAL, first post-freeze priority):** the statement in `SUPPORT.md` §0, verbatim; evidence PRs #212 and #209;
- the `0.001` relative-RMSE diagnostic fails for CUDA versus CPU in all 14 tested family and config cases at `1db86902` (config G 0.0015-0.023); the absolute RMSE
  limit failed in 9 and the max-pixel limit in 5 of 14, tracking intensity scale (#209); the historical 24 tutorial movies gave 0.002899-0.010082;
- no Tier D scientific gate (#61, #73);
- resume does not detect changed settings (#149 deferred);
- no rollback: a failed movie can leave a truncated or earlier per-movie file and an auxiliary `_PS.mrc`; a failed batch withholds the joint
  output and keeps healthy per-movie products (`SUPPORT.md` §6);
- a failed `logfile.pdf` render leaves no `logfile.pdf` (F1, merged); strict in `--aggregate_only`;
- F3/F3b pending (#205); F4 compressed MRC must be validated independently (#214); F5 big-endian mode-0 MRC with nx = 128 not swap-detected;
- EER (D6): damaged fractions are skipped with a warning and the movie publishes; undetected corruption that preserves the pixel count; a truncated EER is a
  shorter movie unless `--expected_frames` or a STAR count is supplied;
- nvCOMP (D1): assumes complete, unmodified input files; a file changing between scan and read is not detected (#215); T3 hardening pending; use `--ingest compact` otherwise;
- optional proprietary dependencies (D2): no project-distributed nvCOMP/nvTIFF-linked binaries; nvTIFF not used;
- host RAM with `--grouping_for_ps` (about +3.8 GiB float, +1.9 GiB compact on 10216), per-geometry VRAM floor, unqualified out-of-memory behaviour (QM),
  EER upsampling 2 memory (Falcon 4, 144 groups, fits at 79,522 MiB on 80 GB);
- inherited macOS test results (`SyntheticRegression`, `MultiGpuScheduling` fail; `NativeMovieStaging` skips);
- `ProfilingKit` has a load-sensitive 30 s subprocess timeout (#209);
- data-dependent patch non-convergence retry (EMPIAR-10641, 10216): host RSS 2.07 GiB with the resident retry versus 7.0 GiB before #197, one retry +504 MiB VRAM on 10641 (#207);
- differences from RELION 5.1: `SUPPORT.md` §0a (#216);
- anything newly found during QF.

## 4. Failed and UNRUN checks

Every check that failed or was not run, with the reason. Original failures are not dropped.

| Check | Status | Reason / evidence |
|---|---|---|
| Frozen-SHA qualification (QF): CPU, CUDA, CUDA+nvCOMP CTest and product campaign | UNRUN | pending freeze |
| CUDA-to-CPU unweighted fallback (#198 C1) | executed natively at `1db86902` | #209: 6/6 identical to pre-#178; injected non-fatal `cudaMalloc` failure falls back identically. Re-run on the frozen SHA pending freeze |
| `ProfilingKit` (CPU, Linux) | FAILED once, then passed | 30 s subprocess timeout at load about 27; passed on rerun (#209) |
| `SyntheticRegression` on macOS | FAILED (inherited) | max pixel diff 23.649856567382812; unchanged from main; reproduced at `67b5315b` |
| `MultiGpuScheduling` on macOS | FAILED (inherited) | tomography endpoint validator; 73 of 74 checks; passed on Linux (#209) |
| `NativeMovieStaging` on macOS | SKIPPED | Linux-only |
| Forced out-of-memory on session initialisation (QM); EER OOM path (the movie fit) | UNRUN | register item pending; #208 |
| Genuine device poisoning | UNRUN | all fatal cases inject error codes; post-RC0 (#213) |
| Native `pbzip2` | UNRUN | absent; `.bz2` tested via a `bzip2 -cd` shim (#204) |
| 10441 and 10641 config G/L product campaign; launcher failure/resume injection; PDF content; second venue; timing | UNRUN | #209 |
| Real 65000, 65002 and 2K EER files; 8K gain at upsampling 1; measured 144-group retry VRAM; converging real-data retry | UNRUN | #208, #207 |
| Truncated raw MRC fails explicitly (F3/F3b) | pending | PR #205 in qualification |
| T3 hardening merged and qualified | pending | #198 register T3 |
| Cross-backend `compare_motioncorr.py --gate backend`, all families | executed as a diagnostic at `1db86902` | relative RMSE fails 14/14 as expected; see §3 and S1 (#209). Not a gate result |
| EER frame-count metadata; RELION pipeliner/GUI without `logfile.pdf`; RELION 5.1 vs standalone on the #186 families | UNRUN | `POST_FREEZE_TEST_PLAN.md` §3a (#216) |
| Example run inventory with Ghostscript on macOS; `run_dataset.py` success path on macOS | UNRUN | local attempt failed only because `gs` is not installed there (`RELEASE_CHECKLIST.md` §8); Linux real-Ghostscript run passed (#209) |
| nvTIFF/LZW, device EER renderer, nvCOMP widening | not in RC0 | #198 register |

## 5. Resource requirements

Peak host RSS and device memory per corpus family. The reference columns are the #186 measurements at main `116eb04a`
(before #178, #187, #195, #196, #197 and #185 merged); the RC0 columns are filled at QF (**pending freeze**). The table after the reference tables gives the qualification measurements at `1db86902`.

Reference provenance. CPU: cpu64, AMD EPYC 7763, 64 cores, SMT off, 226 GB RAM, THP `madvise`, GCC 13.3.0, FFTW 3.3.10, libtiff 4.5.1,
binary SHA-256 `86a43e9f0fa0787ba7eef5270c65eee466857e493d7f6df6daa98de0b28bed53`; config L (`--patch_x 5 --patch_y 5`), dose weighting,
`taskset` to 1 or 8 CPUs, median of the unprofiled runs (`docs/workload_corpus/cpu/README.md`, `cpu/provenance.json`). GPU: 4GPUs GPU0
(A100 80 GB PCIe, driver 570.86.10), `taskset -c 96-103`, `--j 8 --gpu 0`, CUDA 12.8, nvCOMP 5.3.0.16, THP `madvise`, binary SHA-256
`79c88e4ce1f1cb5a445f4da34f195b31edd257d58f4706624678f61fe6d6166c`, inputs in tmpfs; VRAM is the NVML per-process peak (sampled, so a
lower bound) and includes the CUDA context (`docs/workload_corpus/gpu/README.md`, `gpu/provenance.json`).

| Family | Reference CPU RSS GiB, L, `--j 1` / `--j 8` | Reference GPU host RSS GiB, L | Reference VRAM GiB, G / L | RC0 RSS | RC0 VRAM |
|---|---|---|---|---|---|
| tutorial (3710 x 3838 x 24) | 2.75 / 3.19 | 0.4 | 3.2 / 3.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10028 (4096 x 4096 x 16) | 2.17 / 2.67 | 1.6 | 2.6 / 2.7 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10361 (5760 x 4092 x 62) | 11.24 / 11.99 | 1.7 | 11.6 / 12.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10641 (5760 x 4092 x 70) | 12.75 / 13.50 | 7.0 (includes the retry path) | 13.1 / 14.7 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10441 (11520 x 8184 x 50) | 36.31 / 39.09 | 5.0 | 37.0 / 39.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10474 Falcon 3 (4096 x 4096 x 58) | 8.62 / 9.16 | 5.3 | 7.9 / 8.8 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10474 Falcon 4 (4096 x 4096 x 144) | 21.19 / 21.35 | 12.0 | 18.6 / 20.0 | pending RC0 QF | pending RC0 QF |
| EMPIAR-12963 (4096 x 4096 x 39) | 5.91 / 6.47 | 3.7 | 5.5 / 6.2 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10164 (7420 x 7676 x 8) | 3.89 / 5.57 | 2.2 | 4.5 / 4.5 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10216 (4096 x 4096 x 59) | 7.62 / 8.15 | 4.2 | 8.0 / 9.0 | pending RC0 QF | pending RC0 QF |

**Qualification measurements at `1db86902` (PR #209).** Peak host RSS (GiB) of the single-movie worker process from `/usr/bin/time -v`, one movie per
family, `--j 8`, `docs/workload_corpus/families.json` options. Source `1db869025507ac801845b4001b84e6bc0e77a645` (clean clone), host 4GPUs
(4-gpu-vm, 4 x A100 80 GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, nvCOMP 5.3.0.16, THP `madvise`), lane GPU1 and CPUs 104-111, Release builds
(CPU binary `dd86cd41...6b26439`, CUDA+nvCOMP `77db3f92...12a99`; full hashes in `docs/rc0/qual_main_1db86902/raw/summaries/build-info.txt` on PR #209's branch).
One sample per cell; no variability is available. Routes are the `--ingest_witness` values. Not a performance claim.

| Family | cfg | auto route | RSS auto | RSS `--ingest float` | RSS CPU build |
|---|---|---|---:|---:|---:|
| tutorial | G / L | nvcomp | 0.34 / 0.34 | 1.52 / 1.52 | 2.71 / 2.84 |
| EMPIAR-10361 | G / L | compact | 1.54 / 1.53 | 5.67 / 5.68 | 11.06 / 11.28 |
| EMPIAR-10474 Falcon 3 | G / L | compact | 3.16 / 3.16 | 5.02 / 5.14 | 8.53 / 8.65 |
| EMPIAR-12963 | G / L | compact | 2.30 / 2.30 | 3.57 / 3.63 | 5.89 / 5.97 |
| EMPIAR-10216 | G / L | compact | 2.10 / 2.10 | 3.89 / 4.01 | 7.50 / 7.66 |
| EMPIAR-10028 | G / L | float | 1.59 / 1.54 | 1.55 / 1.58 | 2.11 / 2.43 |
| EMPIAR-10164 | G / L | compact | 0.80 / 0.85 | 2.14 / 2.08 | 3.78 / 4.60 |

Other qualification figures (single runs, same host): EER upsampling at the compact route lowered host RSS 34-39 % at upsampling 1 and 43-47 % at 2 and 3
(no saving at -1); a 144-group Falcon 4 movie at upsampling 2 fit on the 80 GB card at 79,522 MiB (calculated 80,520 MiB) with host RSS 21,547 MiB compact versus 40,171
MiB float (PR #208, lane GPU2, CPUs 112-119). EMPIAR-10641 resident retry: peak host RSS 2.07 GiB versus 6.6 GiB (injected fallback) and 7.0 GiB (pre-#197); NVML VRAM
14.24 / 14.68 / 14.68 GiB; one resident retry allocates 504 MiB (10641) / 301 MiB (10216) (PR #207, lane GPU2, CPUs 80-87; VRAM corrected after R-QA1).
`--grouping_for_ps 4` on EMPIAR-10216: about +3.8 GiB host RAM (float) and +1.9 GiB (compact), single samples (PR #204, lane GPU3, CPUs 88-95).

Source tables: `docs/workload_corpus/cpu/README.md` ("Peak RSS" table) and `docs/workload_corpus/gpu/README.md` ("Per-family result"
table). Rule of thumb from the GPU report: VRAM peak is two resident float32 movies (`2 x frames x nx x ny x 4 B`) plus 0.7-4.2 GiB;
estimates for 24, 40 and 48 GiB cards are arithmetic, not runs. Also record: scratch space per run, pinned host memory
(`MOTIONCORR_NVCOMP_PINNED_MAX_MB`, default 256 MiB per worker, `cuda_movie_session.cu:1544-1545`), per-worker RSS and VRAM at 1/2/4 devices,
and the 8-CPU or other CPU cap actually used. Add the two inherited host/VRAM behaviours: `--grouping_for_ps` on the resident CUDA
path downloads one extra Fourier movie to the host (`src/motioncorr_runner.cpp:3210-3217`), and the resident path needs two float-size
stacks on the device (EMPIAR-10441 peaked at 39.3 GiB). EER upsampling 2 quadruples movie storage (measured 79,522 MiB for 144 groups, above).

## 6. Measured performance

One row per measurement. A timing without all fields is not reported. Compare only rows with matching venue, allocation, THP setting,
binary, inputs and storage.

| Field | Meaning |
|---|---|
| source | exact SHA, clean tree |
| binary | path and SHA-256, build type, compiler, CUDA/nvCOMP versions |
| hardware | CPU model, GPU model/UUID, RAM, THP mode, persistence mode, venue |
| resources | CPUs and devices actually allocated, `--j`, `--max_io_threads`, locks held |
| inputs | files and SHA-256, replayed versus distinct movies |
| options | full command line |
| samples | repetitions, interleaving, excluded runs and why |
| variability | min-max or IQR, paired difference with interval |
| output verdict | product comparison performed (tool, profile, result), not only exit status |
| limitations | what the number does not show |

RC0 rows: **pending RC0 QF** (none recorded).

Reference rows (earlier SHAs; context only, not RC0 results):

| Row | source | binary | hardware, resources | inputs, options | samples, variability | output verdict | limitations |
|---|---|---|---|---|---|---|---|
| GPU, tutorial, config L, `--ingest auto` (witness `nvcomp`): 1.43 s whole process, 2 movies | `116eb04a`, clean | SHA `79c88e4c...6166c`, Release | 4GPUs GPU0 A100 80 GB, CPUs 96-103, `--j 8`, THP `madvise`, persistence off | 2 tutorial movies (hashes in `corpus.md`), corpus options, `--gpu 0` | 5 unprofiled repeats, 1.43 [1.41-1.51] s | exit 0 and product count only; no product comparison | tmpfs inputs, one GPU model, process start dominates a 2-movie run (about 1.2 s of 1.4 s) (`docs/workload_corpus/gpu/README.md`) |
| CPU, tutorial, config L, `--j 8`: 10.0 s whole process, 2 movies | `116eb04a`, clean | SHA `86a43e9f...8bed53`, Release `-O3 -DNDEBUG -fopenmp`, GCC 13.3.0 | cpu64, `taskset -c 0-7`, THP `madvise`, `OMP_PROC_BIND` unset | same 2 movies, corpus options, no `--gpu` | 2 of 3 planned clean repeats, 10.0 [9.9-10.0] s | exit 0 and product count; retained tree hashes only | warm page cache, host shared with other users' jobs on other CPUs (`docs/workload_corpus/cpu/README.md`) |
| Dataset endpoint, 24 tutorial movies, 4 x 8 CPUs versus 1 x 32 | `d7339fd` | SHA `ae13ab74...5307d`, Release, CUDA | 4GPUs, 4 A100 (one worker each), fixed 32-CPU budget | 24 tutorial movies, `run_dataset.py`, `--ingest auto` | 6 interleaved reps, publication 10.37 s (IQR 0.82) versus 13.87 s (IQR 0.55), paired difference -4.02 s (CI -4.70, -2.90) | all three arms identical to a single-process single-GPU run on 24 movies (MRC bytes outside the timestamp, normalised STARs, product presence) | host shared throughout; predates #176, #178, #187, #195-#197; not a fixed-budget claim for RC0 (`docs/multi_gpu/scaling/README.md`) |

Per-family GPU and CPU timing tables are in `docs/workload_corpus/{cpu,gpu}/`; do not copy them here without their provenance.

## 7. Sign-off

Maintainer review of this report, the scope decision and the tag are separate steps (`RELEASE_CHECKLIST.md` §10). pending RC0 QF.
