# MotionCorr RC0 support page (DRAFT)

> **This is an EVALUATION RC0, not a stable release** (maintainer decision D7,
> [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198)). It is offered for evaluation and heavy testing.
> No unrestricted or stable support is claimed for CUDA local alignment (see **S1** below), and no scientific equivalence or
> preference for either backend is established.

Status: **draft for RC0, pre-freeze, revision 6** (it stays DRAFT until the freeze; the freeze-time edit is meant to be small: fill the PENDING items below) (after the R-REL and R-REL-B reviews and the R-QA2 audits of PR #201, and the maintainer
decisions D1, D2, T3, D5, D6 and D7). Written against main `483e881d` (after #205 F3/F3b `f67a5866`, the D1/D2 record #199 `a1ab83f2` and #217 T3 `483e881d`, on top of #200 F1 and #210 TST1); the
qualification evidence cited below was gathered at the SHAs stated for each item (mostly `1db86902`). Source line numbers are at `483e881d` and will move; re-check
them against the frozen SHA. Every **Qualification** cell says **pending RC0 QF** (the full CPU + native CUDA qualification of the frozen SHA, register item QF in #198),
unless a row cites evidence. Linux/CUDA command validation by this document's author is **UNRUN**; the qualification lanes on #198 are cited as evidence, not re-run here.

**Qualification state, completed versus pending.** *Completed* (per-item, pre-freeze, on the stated SHAs): Q1 (`1db86902`, PR #209), raw-MRC staging M1 (#204),
EER compact route E1 (#208), resident retry R1 (#207), S1 diagnosis (#212), F3/F3b fail-closed reads (#205), T3 checked arithmetic (#217), the C5 timing
measurement (#218), and smaller-GPU memory admission QM (PR #225, on `483e881d`, audited by R-QM; documented limits in §8 "GPU memory"). *Pending QF on the frozen SHA* (placeholders, nothing here has been run on it): CTest on CPU, CUDA and CUDA+nvCOMP; the route/product campaign;
multi-GPU 1/2/4; the adapted compact-ingest matrix (#123); `CpuDoseSymmetry` (if #220 merges); whether PR #223 (the `MultiGpuScheduling` test-harness fix) is in the frozen SHA. The macOS statement is made (§1: builds and runs; not qualified; known CPU CTest differences). `RC0_ACCEPTANCE_REPORT.md` carries the per-item detail.

MotionCorr is an experimental standalone build of RELION 5.1's motion correction (`ad0b230c`, see
`SOURCE_MANIFEST.txt`). It is not an official RELION or MotionCor2 release. An RC0 evaluation release is not a
scientific non-inferiority certificate (Tier D below).

## 0. Most important known limitation: S1 (PROVISIONAL, priority for heavy testing)

> **S1 — CPU versus CUDA local alignment (PROVISIONAL).** In the tested movies (EMPIAR-10216, 10474 Falcon 3 and 12963, 5×5 patches), CPU and CUDA local-alignment products differ substantially (relative RMSE 0.43–0.60). This was already present before RC0 (`116eb04a`). The difference is amplified by patch acceptance and the inherited unweighted polynomial fit. It also occurs among trajectories accepted on both backends; matching convergence status does not guarantee agreement. In the inspected cases the initiating events are frames where two cross-correlation peaks are within a few float ulps and the two backends order them differently. Making CUDA use the CPU tie rule (#70) changed two outputs slightly but did not explain the discrepancy. Whether the small map differences are pure rounding is not established. Other CUDA defects are not excluded, and no scientific equivalence or preference for either backend is established.

Evidence: diagnosis [PR #212](https://github.com/KingAlejandro/MotionCorr-standalone/pull/212) (`docs/rc0/diag_s1/`, on that branch) and the
backend diagnostic table in [PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209) (`docs/rc0/qual_main_1db86902/`,
on that branch). Figures from #209 (main `1db86902`, `compare_motioncorr.py --gate backend`, relative RMSE CPU versus CUDA, config L =
`--patch_x 5 --patch_y 5`): 10474 Falcon 3 0.5999, 12963 0.499, 10216 0.4344; tutorial 0.0084, 10361 0.0091, 10164 0.0013, 10028 0.014. Config G
(global only) is 0.0015-0.023 on all seven families. Global-shift gates are met in all 14 cases. Consequences for users:

- Do not treat CUDA local alignment (`--patch_x`/`--patch_y` of 3 or more with `--gpu`) as validated against the CPU backend on movies with
  non-converging patches. Compare both backends on your own data before relying on either.
- Treat the CPU backend as the reference for local alignment in RC0 for comparison purposes only; that is not a statement that it is more
  correct.
- This is the first priority item of the post-freeze campaign (`POST_FREEZE_TEST_PLAN.md`).

## 0a. Coming from RELION 5.1 (`relion_run_motioncorr --use_own`)

Where this program behaves differently from RELION 5.1's built-in CPU motion correction (RELION `ver5.1` at `ad0b230c`; the extraction commit
`4499be23` carries an identical `motioncorr_runner.cpp`). Tracking issue:
[#216](https://github.com/KingAlejandro/MotionCorr-standalone/issues/216), whose §1-§6 this table summarises; only items marked **Verified**
(checked in source or evidence) or **Decided** (maintainer decision on #198) there are listed. Details and line numbers are in the sections cited.

| Area | RELION 5.1 | Standalone | Status |
|---|---|---|---|
| Defect/hot-pixel replacement randomness | cached Box-Muller deviate survives re-seeding; multi-threaded runs are not reproducible | `rnd_gaus()` re-seed fix and deterministic defect seeding (`--seed`, default 1); multi-threaded runs identical to single-threaded. **Expect pixel differences:** standalone `--j 1` vs RELION `--j 1` is exact on 1/24 tutorial movies (median relative RMSE about 0.0069) | Verified (`SOURCE_MANIFEST.txt`, `docs/gate_contract.md` §7, #20) |
| `--interpolate_shifts` (experimental) | recentering origin already zeroed, frames 1..n-1 not recentered | origin saved first (#97); deliberate divergence | Verified (`SOURCE_MANIFEST.txt`) |
| Direct movie or wildcard input | crashes before processing (missing per-movie metadata) | works; optics group bound correctly (#172, #173) | Verified |
| `--gpu` with `--use_own` | `--use_own` is CPU only; `--gpu` is a per-MPI-rank device list for the MotionCor2 route | native CUDA backend on **exactly one** device id; a device list is rejected; `--use_motioncor2` still passes the list through | Verified (`src/motioncorr_runner.cpp:194, 342-370`) |
| Multi-GPU | `relion_run_motioncorr_mpi` spreads movies over MPI ranks | no MPI runner; use `tools/multi_gpu/run_dataset.py` (one process per device), §4 | Verified (PR #209) |
| CUDA versus CPU products | n/a | global alignment: relative RMSE 0.0015-0.023 on the corpus; local alignment on partly converging movies 0.43-0.60 (**S1**, §0); the 0.001 diagnostic fails | Decided (D7): evaluation RC0, no unrestricted CUDA local-alignment claim |
| nvCOMP GPU Deflate ingest | n/a | only with `-DUSE_NVCOMP=ON` (default OFF); trusted-input precondition, §7; checked arithmetic on the pre-decode path (T3, #217 merged) | Decided (D1 option 1, D2 interim policy A, T3) |
| Truncated or short raw MRC movie, gain reference, defect map | read errors ignored; products published from partly unread memory | the movie fails explicitly ("is truncated or unreadable"); a truncated gain or defect map fails every movie and the job | Decided (D5); **merged** (#205, `f67a5866`), §6 item 5 |
| Frame-count checking | not checked | `--expected_frames` and the per-movie STAR counts `rlnNrOfFrames` / `rlnTomoTiltMovieFrameCount` are compared with the **decoded** frame count; a mismatch fails the movie (`:454-478, 2150-2155`) | Verified |
| `--only_do_unfinished` | skips a movie whose output micrograph file exists | re-processes unless the products are complete (`isMovieComplete`, §5); a changed-settings resume is still not detected (#149), as in RELION | Verified |
| Pinned ingest, `--aggregate_only` | n/a | `--ingest nvcomp/compact/float` refuses a movie that cannot use that route; `--aggregate_only` is new and strict | Verified |
| `logfile.pdf` after a failed Ghostscript render | sub-reports get empty placeholders; `logfile.pdf` is built by concatenation | normal mode leaves **no** `logfile.pdf` (F1, #200 merged); `--aggregate_only` fails strictly, §6 | Verified for the standalone |
| Worker reports; failed movie | per-movie files may remain | `--skip_report_pdf` for multi-GPU workers; no rollback: partial or earlier per-movie files and an early `_PS.mrc` can remain, joint outputs withheld, §6 | Verified |
| Corrupt EER fractions | skipped with a warning (inherited) | preserved: wrong-pixel-count fractions are skipped and the movie publishes; supply `--expected_frames`, §2 | Decided (D6) |
| Compressed MRC integrity | decompressor exit status not checked (inherited) | unchanged; validate inputs with `xz -t`/`zstd -t`/`bzip2 -t`, §6 item 6 | Decided (D5/F4, fix #214) |
| MRC mode 0, early binning, dose-weighting voltages | mode 0 read as signed int8; early binning on by default when `--bin_factor` is not 1; dose weighting only at 100/200/300 kV | unchanged. **GPU users:** with `--bin_factor` other than 1, default early binning bypasses the resident CUDA session and compact host staging (the movie takes the `float` route and the global FFT runs on the CPU); late binning needs `--no_early_binning` (`src/motioncorr_runner.cpp:2278, 2383`; §2, §3). RELION users who pass `--bin_factor 2` expecting lower GPU memory use will not get the resident path by default | Verified |
| Options | all RELION 5.1 `relion_run_motioncorr` options | all still parsed; new, additive: `--seed`, `--expected_frames`, `--ingest`, `--ingest_witness`, `--profile`, `--profile_device_timing`, `--sync_output`, `--skip_report_pdf`, `--aggregate_only`. The only change in meaning is `--gpu` under `--use_own` | Verified |

### Not yet verified (#216 "To verify"; nothing here is asserted)

- **EER frame-count metadata.** For EER the decoded count is `fractions / --eer_grouping` (trailing remainder dropped). Whether a STAR that records
  the raw fraction count (for example a RELION 5 tomography import) would make the standalone fail movies RELION processes has not been shown.
  It is a test row in `POST_FREEZE_TEST_PLAN.md` §3a.
- **RELION's end state without Ghostscript, and the pipeliner/GUI.** Whether RELION leaves a different `logfile.pdf` state without Ghostscript, and
  whether the RELION pipeliner/GUI (which lists `logfile.pdf` as a job output node) tolerates its absence, has not been checked.
  Test row in `POST_FREEZE_TEST_PLAN.md` §3a.

Open policy questions (drop-in replacement, CPU parity target, upstream sequencing) are discussed on #216 and are not decided here.

## 1. Supported, experimental and unsupported

| Class | Configuration | Basis | Qualification |
|---|---|---|---|
| Supported (intended) | `--use_own` on CPU, Release build, **Linux x86_64** | CPU CTest suite; `README.md` build section | pending RC0 QF |
| Not qualified | `--use_own` on CPU, Release build, **macOS arm64: builds and runs; not qualified; known CPU CTest differences.** `SyntheticRegression` fails because libc `rand()` differs from glibc, so the same `--seed` gives different hot-pixel replacement and therefore different output bytes on macOS and on glibc Linux ([#222](https://github.com/KingAlejandro/MotionCorr-standalone/issues/222)); `MultiGpuScheduling` fails from a test-harness `/var` symlink issue, fixed by [PR #223](https://github.com/KingAlejandro/MotionCorr-standalone/pull/223) (**PENDING MERGE**; whether it is in the frozen SHA is a freeze-time placeholder) | W-MAC, #198; `RELEASE_CHECKLIST.md` §3 | n/a |
| Supported for evaluation | `--use_own --gpu <one id>` on a CUDA build (`-DCUDA=ON`), one process per device. **Local alignment: no unrestricted or stable claim, see S1** | `src/motioncorr_runner.cpp:342-405`; qualification PRs #204, #207, #208, #209 | at `1db86902` (#209): CTest 89/89 on the no-nvCOMP build; the real-data route-invariance campaign ran on the CUDA+nvCOMP binary, not on a no-nvCOMP binary; frozen SHA pending RC0 QF |
| Supported for evaluation | Several GPUs through `tools/multi_gpu/run_dataset.py` (one process per device) | §4; `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`; PR #209 | 1/2/4 workers x 24 tutorial movies passed at `1db86902` including a real-Ghostscript `logfile.pdf` (#209); frozen SHA pending RC0 QF |
| Experimental | nvCOMP device Deflate ingest (`-DUSE_NVCOMP=ON`, default OFF); assumes complete, unmodified input files, §7 | `CMakeLists.txt:140`; D1 (option 1), D2 (interim policy A), T3 merged | qualified for route invariance at `1db86902` (#209); frozen SHA pending RC0 QF |
| Experimental | `--interpolate_shifts` | help text: "(EXPERIMENTAL)", `src/motioncorr_runner.cpp:212` | pending RC0 QF |
| Not qualified | Every option or input not named in §2 and §3 | no evidence on this page | n/a |
| Unsupported | `--gpu` with a device list under `--use_own` | rejected, `src/motioncorr_runner.cpp:342-370` | refusal verified locally on a CPU build only, §4 |
| Unsupported | `--use_motioncor2` (needs the external MotionCor2 executable) | not part of this program; `src/motioncorr_runner.cpp:222` | n/a |
| Unsupported | One process driving several GPUs (#175), MPI | #175 is parked; `src/motioncorr_runner.cpp:362-367` says the repository has no MPI runner | n/a |
| Unsupported | Resume with changed processing settings in the same `--o` (#149 deferred), §5 | #149 | n/a |
| Not in RC0 (NO-GO) | nvTIFF/LZW device route (#141/#152): **not used by RC0** | #198 register L1: NO-GO for RC0 | n/a |
| Not in RC0 (NO-GO, parked) | nvCOMP Deflate widening to 8-bit samples and any rows-per-strip (#138), parked as [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206) | #198 register T1: NO-GO for RC0; reopen after RC0 only with a real deposited u8/multi-row Deflate dataset, a strips-per-frame admission floor and D1 | n/a |
| Optional, **PENDING MERGE** | CPU dose-weighting symmetry (#179 lean port, #220) under a qualified-toolchain contract, §9 | #198 register C5; decided acceptable for RC0 under the contract, expected to merge before freeze | PENDING MERGE; `CpuDoseSymmetry` required at QF |
| Not in RC0 (parked post-RC0) | device EER renderer ([#193](https://github.com/KingAlejandro/MotionCorr-standalone/issues/193) option 2, [PR #211](https://github.com/KingAlejandro/MotionCorr-standalone/pull/211)); #183 / #219 CPU patch-phase update (C7) | #198 register: E2 parked post-RC0 (D9); C7 parked | n/a |
| Not in RC0 (closed, no-go) | #181 exact interpolation cache; #182 | #198 register C6, C9 | n/a |

CUDA architecture: `CMakeLists.txt:118-119` defaults `CMAKE_CUDA_ARCHITECTURES` to 80 unless the user or
`CUDAARCHS` sets it. An sm80 binary is not a statement that other devices work.

## 2. Input capability matrix (from current source)

Routes: **CPU** = `--use_own` without CUDA, host reader into float frames. **CUDA float** = host decodes to a float
movie, device does the rest. **CUDA compact** = host decodes into the file's native integer type, the device expands
to float and applies gain. **CUDA nvCOMP** = Deflate strips are decompressed on the device
(`USE_NVCOMP=ON` build only).

`--ingest_witness FILE` appends one line `<movie path> <value>`, `<value>` being `nvcomp`, `compact` or `float`
(`src/motioncorr_runner.cpp:2437-2450`). It writes nothing else. It records the route **selected** for a movie that
reached that point; it is not a record of completion or success:

- a movie skipped by resume is filtered earlier and has no line (`:559-565`);
- a pinned `--ingest` that cannot be honoured fails before the line is appended (`:2327-2331, 2424-2445`), so a
  refusal has no line of its own (use a positive control to prove the intended route);
- compact and float lines are written before the host decode (`:2437-2455`), so a movie that is damaged and then fails
  to decode can still have a line.

On a CPU-only build, and on a CUDA build with no resident CUDA session, the value is `float`. **Early binning** (`--bin_factor` other
than 1 turns it on by default) bypasses the resident session and the compact staging (`:2278`, `:2383`), so such a movie always takes the
float route; late binning needs `--no_early_binning`. Session-initialisation failure also gives `float`.

| Input | Sample type | Compression | CPU | CUDA float | CUDA compact | CUDA nvCOMP | Witness on CUDA, `--ingest auto` | Source | Qualification |
|---|---|---|---|---|---|---|---|---|---|
| TIFF | uint16 | Deflate (8 or 32946) that meets **every** nvCOMP admission test listed below the table | yes | yes (`--ingest float`) | yes (`:2377`) | **yes**, with a live resident session and a successful ingest | `nvcomp` (nvCOMP build) else `compact` | `src/acc/cuda/cuda_movie_session.cu:1425-1468` | pending RC0 QF |
| TIFF | uint16 | Deflate that fails any admission test, or whose ingest declines for budget or arena reasons | yes | yes | yes | declines and logs "nvCOMP ingestion declined (...); using the host reader." (`cuda_movie_session.cu:1499`; budget refusals `:1598, 1740`) | `compact` | same | pending RC0 QF |
| TIFF | uint16 | any other codec LibTIFF decodes (LZW, none, ...) | yes | yes | yes | no (not Deflate) | `compact` | `:2377-2378`; `cuda_movie_session.cu:1453-1454` | pending RC0 QF |
| TIFF | uint8 | any LibTIFF codec | yes | yes | yes | no: requires 16 bits, `cuda_movie_session.cu:1450` | `compact` | `:2377-2378` | pending RC0 QF |
| TIFF | int8, int16 (signed samples) | any | yes | yes | **no**: signed TIFF is read as `SChar`/`SShort`, which the compact TIFF test excludes (`:2377-2378`) | no (also fails the nvCOMP unsigned-sample test) | `float` | `src/rwTIFF.h:119-129` | pending RC0 QF |
| TIFF | float32 | any | yes | yes | no | no | `float` | `src/rwTIFF.h:131` | pending RC0 QF |
| TIFF | 4-bit packed (K2/K3 special case, 8-bit TIFF of K3 super-resolution dimensions) | any | yes | yes | no | no | `float` | `src/rwTIFF.h:100-113` | pending RC0 QF |
| MRC / MRCS | mode 6 (uint16) | none | yes | yes | yes | n/a | `compact` | `src/rwMRC.h:213`; `:2379-2381` | pending RC0 QF |
| MRC / MRCS | mode 1 (int16), mode 0 (**int8, signed**) | none | yes | yes | yes, staged in the signed type (#195) | n/a | `compact` | `src/rwMRC.h:200-205`; `:2379-2381, 2400-2422` | pending RC0 QF |
| MRC / MRCS | mode 2 (float32), mode 12 (float16), mode 101 (4-bit) | none | yes | yes | no | n/a | `float` | `src/rwMRC.h:206, 216-227` | pending RC0 QF |
| MRC / MRCS | modes 3, 4 (complex); any other mode | none | refused at read | refused | refused | n/a | n/a | `src/rwMRC.h:209-228` | pending RC0 QF |
| `.mrc/.mrcs` + `.bz2`/`.xz`/`.zst` | per header | external `pbzip2`, `xz` or `zstd` must be on `PATH`. One sequential frame reader (`:2473`); only `pbzip2` takes a thread count (`-cdkp<N>`, N = the IO-thread setting, `:2140`), `xz -cdk` and `zstd -cdk` take none | yes | yes | **no** (excluded from compact and nvCOMP) | no | `float` | `src/image.h:1824-1861, 1896-1907`; `src/motioncorr_runner.cpp:2298, 2383, 2473` | pending RC0 QF |
| EER | counts, rendered on the host; square 2048 x 2048 or 4096 x 4096 only | EER | yes (float movie) | yes | **yes**, only if `eer_grouping` x (4 if `--eer_upsampling -1`, else 1) <= 65535, rendered into uint16 (#196) | n/a | `compact`, otherwise `float` (logged: "can exceed 65535 counts per pixel; using the float movie") | `:2357-2372`; `src/renderEER.cpp:150-155, 193-195, 232-236` | pending RC0 QF |

**Compact-ingest matrix (#123): placeholder.** The adapted compact-ingest support matrix of #123 is to be run on the frozen executable as part of QF. Result: pending RC0 QF.

Shape and format restrictions the cells above do not repeat:

- **MRC mode 101 (4-bit)** is refused when both nx and ny are odd (`src/rwMRC.h:219-225`).
- **EER upsampling.** The program accepts `-1`, `1`, `2` and `3` on a 4096 x 4096 detector (`src/renderEER.cpp:150-155`); the option
  help says "1 or 2". A 2048 x 2048 movie, and a movie with the 2-bit sub-pixel encoding (compression tag 65002), take only 1 and 2
  (`:219-236, 573-593`). A TIFF-wrapped EER whose first page is a sum (the TIA variant) is not supported (`:193-195`).
- **EER corpus coverage.** All seven corpus EER files are encoding 65001 at 4096 x 4096. Encodings 65000 and 65002 and the 2K
  detector were exercised only with **synthetic** movies; no real 65000, 65002 or 2K file was run (W-EER-Q, [PR #208](https://github.com/KingAlejandro/MotionCorr-standalone/pull/208)
  and #198 log).
- **EER frame count.** Trailing fractions are dropped: the frame count is `fractions / eer_grouping` with integer
  division (`src/motioncorr_runner.cpp:2134-2136`). This differs from `--group_frames`, which gives a non-dividing remainder to the
  **last** groups (`:2185-2195`).
- **EER corruption and missing frames (D6, inherited RELION behaviour).** A fraction whose decoded pixel count is wrong is skipped
  with a WARNING and **the movie still publishes** (`src/renderEER.cpp:564-567`, "This frame is skipped"). Two limits follow:
  - **undetected corruption:** corruption that leaves the pixel count right is not detected at all;
  - **missing frames:** a truncated EER file is processed as a shorter movie unless `--expected_frames` or a per-movie STAR frame count
    is supplied. **Supply one** for every EER dataset. `--expected_frames` and the STAR counts are the **grouped** frame count, not the number of fractions:
    `grouped count = raw fractions / --eer_grouping`, **integer division** (`src/motioncorr_runner.cpp:2134-2136`). Example: 2331 fractions at
    `--eer_grouping 40` give 58 groups, and so do 2330; give 58, not 2331 (a raw count would make every valid movie fail). The check detects a
    **mismatch in the expected grouped frame count** (`:2150-2155`); it does **not** detect every shortened or damaged file, because losing
    trailing fractions without changing the quotient is invisible.
  Preserved unchanged for RC0 by maintainer decision D6; identical before and after #196 and on both routes (#198 register E-1).
- **EER damaged-input robustness (EER-MS, #221): release disposition PENDING.** Memory safety of the inherited host decoder on malformed or truncated EER
  input is **not established**. The decoder's 7-bit loops read without a strip-length termination check, and its decode vectors are sized from
  `frame_sizes * 2` with no per-emission capacity check (`src/renderEER.cpp:416-555`). Host out-of-bounds access and a process abort on malformed or truncated EER
  have been **reported** ([#221](https://github.com/KingAlejandro/MotionCorr-standalone/issues/221)); independent verification is in progress, and whether RC0 ships a fix or
  a documented limitation is **PENDING**. Until then this page does **not** claim the EER input path is stable on damaged input, and EER inputs are assumed
  complete and unmodified (like nvCOMP under D1). The D6 statement above (a wrong-pixel-count fraction is skipped with a warning and the movie publishes) is unchanged.
  The uint16 count bound itself holds only for decoder executions within valid buffer bounds, where emitted positions are strictly increasing
  (`src/renderEER.cpp:438-463, 484-510, 537-555`) and the render mapping is injective except for the four-to-one 4K to 2K case.
- **EER defect replacement** on the compact EER route uses the host path (`Iframes_u16` x gain); the sparse device gather is reachable only with
  nvCOMP input (PR #208).
- **EER memory (single runs per arm, PR #208, A100 80 GB, main `1db86902`).** `--eer_upsampling 2` doubles both dimensions
  (`src/renderEER.cpp:356-375`), so every movie buffer is four times larger (upsampling 3: sixteen times). Host RSS with the compact route
  was 34-39 % lower than the float route at upsampling 1 and 43-47 % lower at 2 and 3; there was no saving at -1 (not investigated). Device
  memory is unchanged, because the resident device buffers are float whatever the host staging type. A 144-group Falcon 4 movie at
  upsampling 2 **completed with 79,522 MiB of sampled NVML process VRAM** (one run per arm, 81,920 MiB card, about 2.3 GiB remained; calculated 80,520 MiB),
  with host RSS 21,547 MiB (compact) versus 40,171 MiB (float). That figure is a **sample, not an upper bound or a guaranteed fit**, and the out-of-memory
  path was not exercised. There is **little observed headroom**: upsampling 2 on large EER movies is unqualified on any card below 80 GB and marginal on 80 GB. The
  earlier #186 estimate was about 75 GiB, not run (`docs/workload_corpus/gpu/README.md`); the measurement above supersedes it.

Corpus labels (corrected in this PR, `docs/workload_corpus/corpus.md` and `families.json`):

- **The RELION tutorial movies are 16-bit Adobe-Deflate TIFF, RowsPerStrip 1, no predictor, unsigned integer samples, little-endian,
  width 3710 x height 3838** (W-TIFF, TIFF inventory by `tifffile`, [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206)); sample values are at
  most 68. This agrees with the nvCOMP admission rule (16 bits, one row per strip) and with the #186 witness `nvcomp`. The earlier label
  "u8 Deflate TIFF" and the 3838 x 3710 order were wrong.
- **EMPIAR-10164 is MRC mode 0, which this program reads as signed int8** (`src/rwMRC.h:200-202`); the maximum byte value in the corpus
  movies is 90, so no value changes under signed reading (W-MRC-Q, [PR #204](https://github.com/KingAlejandro/MotionCorr-standalone/pull/204)).
- The #186 GPU table (main `116eb04a`) records `float` for every MRC family. #195 (merged `faf5fbdf`) added the raw
  integer MRC compact route; PR #204 and #209 witness `compact` for modes 0 and 1 and `float` for float32 MRC. The matrix follows current source.

Positive nvCOMP admission tests (all must hold for every selected frame; any failure declines to the host reader, and
under a pinned `--ingest nvcomp` fails the movie), `src/acc/cuda/cuda_movie_session.cu:1425-1490`:

| Test | Line |
|---|---|
| native byte order | 1425 |
| no predictor (`TIFFTAG_PREDICTOR` = 1) | 1444 |
| unsigned integer samples | 1447 |
| fill order most-significant-bit first | 1448 |
| width and height equal the movie's, for every selected frame | 1449 |
| 16 bits per sample, one sample per pixel, contiguous planar layout | 1450-1452 |
| Deflate or Adobe Deflate compression | 1453-1454 |
| one full row per strip (strip count = ny, strip size = nx x 2 bytes) | 1458-1461 |
| per-strip compressed size of at least 7 bytes and below 4 GiB | 1468 |
| each strip offset readable from the TIFF directory (T3, #217) | 1470-1480 |
| each strip's offset plus byte count fits a file offset (checked arithmetic, T3, #217) | 1484-1488 |

**Checked arithmetic (T3, #217, merged `483e881d`).** An overflow in the pre-decode size arithmetic, or a strip offset LibTIFF cannot supply, gives a **named
decline** (`NotApplicable`, "nvCOMP ingestion declined (size arithmetic overflow: ...)" or "strip offset not readable from the TIFF directory"):
`--ingest auto` falls back to the host reader, and a pinned `--ingest nvcomp` refuses the movie
(`src/acc/cuda/cuda_movie_session.cu:1477-1490, 1523-1530`; `src/acc/cuda/cuda_checked_arith.h`; no CUDA error is recorded, so the caller maps it to `NotApplicable`). Valid inputs take the same route as before. This
does **not** change D1: a corrupt Deflate **body** is still outside what MotionCorr can make safe (§7).

A matching file can still decline later on pinned-memory, arena or chunk budgets (`:1598, 1740`; the pinned cap is
`MOTIONCORR_NVCOMP_PINNED_MAX_MB`, default 256 MiB per worker, `:1580-1589`). The witness is `nvcomp` only after a
successful ingest.

### Pinned `--ingest` semantics

`--ingest auto|nvcomp|compact|float` (default `auto`, `src/motioncorr_runner.cpp:157-163`). Valid only with
`--use_own` (`:236`). Any value other than `auto` makes a movie that cannot take that route **fail**, instead of
silently taking another (option help, `:157`).

| Value | Behaviour | Source |
|---|---|---|
| `auto` | nvCOMP if admitted, else compact if admitted, else float | `:2333-2336` |
| `nvcomp` | refused at start-up on a CPU-only build (`:244-245`) and on a CUDA build without `USE_NVCOMP=ON` (`:248-249`). Per movie: error if the device ingest did not run (`:2327-2331`) | as cited |
| `compact` | refused at start-up on a CPU-only build (`:244-245`). Per movie: error if no resident session or the movie is not an eligible type (`:2424-2430`) | as cited |
| `float` | always accepted; disables nvCOMP and compact | `:2297, 2363, 2382` |

Verified locally on a macOS CPU-only Release build (exit status 1 for each refusal): `--ingest compact` and
`--ingest nvcomp` (error at line 245), `--ingest bogus` (line 163); `--ingest float` and `--ingest auto` exit 0, and the
witness for the 128 x 128 MRCS fixture reads `float`. The per-movie refusals need a CUDA build and are **UNRUN**.

## 3. Option matrix

"Source" cites where the option is parsed or where behaviour changes. The CPU column describes the code, not a
qualification. The CUDA column says only what source shows; "not claimed" means this page has no evidence either way.

| Option | CPU | CUDA (`--gpu`) | Source | Qualification |
|---|---|---|---|---|
| Global alignment only (`--patch_x 1 --patch_y 1`, default) | yes | yes, device alignment (resident Fourier frames) | parse `:187-188`; execution `:3343-3349` | pending RC0 QF |
| Local patches (`--patch_x N --patch_y M`) | yes; a value of exactly 2 prints "too small ... Patch based alignment will be skipped" (`:308-314`) | yes, device patch alignment (`:3548-3557`) with resident retry for non-converged patches (#197) | as cited | pending RC0 QF |
| Dose weighting (`--dose_weighting`, `--angpix`, `--voltage`, `--dose_per_frame`, `--preexposure`) | yes; **voltage must be within 2 kV of 100, 200 or 300** or the movie fails | yes, in VRAM when a session is resident; CPU fallback exists | `:4094-4107, 4121` | pending RC0 QF |
| `--save_noDW` | yes (streamed unweighted sum, #178); **needs `--dose_weighting`**: without dose weighting the unweighted sum is the main `.mrc` and no `_noDW.mrc` is written | yes. At `1db86902` six CPU-backend checks (CUDA-linked binaries run **without** `--gpu`) and **one** injected recoverable CUDA-to-CPU fallback under `--gpu` (injected `cudaMalloc` failure #16) all matched the pre-#178 build `d7171b81` (PR #209); not real out-of-memory or device poisoning; frozen-SHA rerun pending | `:3379` (`pre_dw_sum_needed`), `:4067-4073`, resume `:792`; #198 item C1 | pending RC0 QF |
| `--even_odd_split` (`_EVN.mrc`, `_ODD.mrc`) | yes | yes | `:3379, 3981-3989` | pending RC0 QF |
| `--bin_factor` (non-integer allowed) | yes; early binning is on by default when binning; **the binned dimensions must both be even** or the movie fails | early binning (the default when binning) skips the resident session and compact staging, so the movie takes the float route and the global FFT stays on the CPU; late binning needs `--no_early_binning`. Route-invariance of late/early binning was checked on valid input (PR #204) | `:182, 217-219, 2278, 2383, 3135-3139, 3165-3171`; late binning `:4973-4975` | pending RC0 QF |
| `--group_frames N` | yes; fewer than 3 groups after grouping skips the movie; a non-dividing remainder goes to the **last** groups (`:2185-2195`) | identical across routes for `--group_frames 4` (PR #207) | `:2174-2195` | pending RC0 QF |
| `--eer_grouping`, `--eer_upsampling` | yes; see §2 for accepted values, shapes and the trailing-fraction rule | compact route only within the uint16 limit; **upsampling 2 quadruples the movie storage: a 144-group Falcon 4 movie completed with 79,522 MiB of sampled NVML process VRAM on an 81,920 MiB card, one run per arm, about 2.3 GiB observed remaining (2,398 MiB); little observed headroom, not a guaranteed fit** (§2, PR #208) | `:2357-2372` | pending RC0 QF |
| Gain (`--gainref`, `--gain_rot`, `--gain_flip`) | yes; size must match the movie or the movie fails | yes; device gain applied on the compact and nvCOMP routes | `:2217-2230` | pending RC0 QF |
| Defect file (`--defect_file`; `--skip_defect`; `--seed`) | yes; a SerialEM-format `.txt` is rejected. `--skip_defect` skips **both** the automatic hot-pixel detection and the correction with the supplied defect mask (both sit inside `if (!skip_defect)`) | replacement neighbours are read from the typed host staging on the compact routes (`:3043-3058`) and uploaded as sparse replacements; the sparse **device** gather (`gatherFrameSamples`) is used only for nvCOMP input, which has no host frames (`:2968-2982, 3081-3088`) | `:190, 267-272, 2746, 2853`; `cuda_movie_session.cu:1258` | pending RC0 QF |
| `--first_frame_sum`, `--last_frame_sum` | yes; frames outside the range are not used at all | not claimed | `:2161-2169` | pending RC0 QF |
| `--grouping_for_ps`, `--ps_size` (`_PS.mrc`) | yes | **on the resident CUDA path this downloads the whole Fourier movie to the host** (`:3229-3236`): about one complex movie of extra host RAM. Measured on EMPIAR-10216 with `--grouping_for_ps 4` (single samples, PR #204): about **+3.8 GiB** on the float route and about **+1.9 GiB** on the compact route | `:3227-3330`; failure behaviour, §6 | pending RC0 QF |
| `--float16` | yes, requires `--grouping_for_ps > 0` | not claimed | `:205, 225-226` | pending RC0 QF |
| `--expected_frames` | yes; a different decoded frame count fails the movie. It is a **fallback**: a per-movie STAR frame count overrides it | same | `:173, 1016-1024, 2150-2155` | pending RC0 QF |
| Direct `--i 'glob'` input with `--angpix` and `--voltage` | yes | same | `README.md`; `:322-328` | pending RC0 QF |
| Tomography STAR input | yes (`Runner_tomography` test; the dataset endpoint check lives in `tests/test_tomography_endpoint.py`, run by `MultiGpuScheduling`) | same | `src/motioncorr_runner.cpp:413` | pending RC0 QF |

## 4. Multiple GPUs

- The binary supports **one** device id per process. `--gpu 0:1` under `--use_own` is rejected with exit status 1 and a
  message pointing to `tools/multi_gpu/` (`src/motioncorr_runner.cpp:362-367`; `SOURCE_MANIFEST.txt`, local-change
  list). Verified locally on a CPU-only build; the CUDA-build refusal is the same code path ahead of `#if _CUDA_ENABLED`.
- Several devices: `tools/multi_gpu/run_dataset.py` partitions the input STAR, runs one `motioncorr` per device, then runs one
  `--aggregate_only` owner and publishes the joint STAR and `logfile.pdf`. `dataset_ready` is the completion state;
  `workers_complete` is not (`tools/multi_gpu/run_dataset.py:1-7`, `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`).
- `run_dataset.py` refuses an existing `--out`, and a device list requires Linux child-subreaper support
  (`tools/multi_gpu/run_multi_gpu.py`, `--devices` handling).
- **Ghostscript is required** for the dataset endpoint. The aggregate step runs strict PDF rendering. Locally, with no
  `gs` installed, two CPU workers completed and the aggregate failed with "Aggregate PDF generation failed"
  (`src/CPlot2D.cpp:93`), so `run_dataset.py` exited 3.
- **Verified at `1db86902`** (W-QUAL, [PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209), 4GPUs): 1, 2 and 4 workers on the
  24 tutorial movies, configs G and L, 6/6 dataset-endpoint PASS; every launcher worker was physically witnessed on its intended, distinct GPU UUID; normalised products (labels and extended headers
  included, only the writer timestamp masked) identical across worker counts and to a single process; joint STAR and a 30-page `logfile.pdf` rendered with real Ghostscript 10.02.1. A mixed tutorial + 10641 + EER 2-worker run was identical to
  a 1-worker run. **Witnessing limit:** the 28 original single-process CUDA campaign runs (route invariance, #178 checks) and the injected-fallback pair were
  UUID-pinned with `CUDA_VISIBLE_DEVICES` but **not physically witnessed**; three later runs and all launcher workers were. Not run: 10441 and 10641 config G/L alone, launcher failure/resume injection, PDF page content comparison, real
  out-of-memory, a second venue, timing. Re-verification on the frozen SHA is pending RC0 QF.
- Earlier scaling evidence (not RC0): 4x8 CPUs was 1.34x (24 movies) and 1.68x (96 movies) faster than 1x32 to publication
  (`docs/multi_gpu/scaling/README.md`; source `d7339fd`, 4GPUs). Tomography on real data is unmeasured.
- Throughput scaling at a fixed budget is not a support claim.

## 5. Resume

`--only_do_unfinished` treats a movie as complete when its products exist and each passes a limited check
(`src/motioncorr_runner.cpp:785-827`, `isMovieComplete`):

- each requested MRC (`.mrc`, and `_noDW`, `_EVN`/`_ODD`, `_PS` when requested) has a parseable header, float or float16
  type, `nz = 1` and at least as many bytes as its own header implies (`completeMrc`, `:701-716`);
- the per-movie STAR has positive size fields, the same movie name, a shift for every frame, finite values, and the
  expected frame count when one is given (`:791-821`).

It does **not** compare the MRC geometry with the STAR, and it does **not** compare the settings of the earlier run
with the current ones. Geometry and sampling cross-checks exist only in `--aggregate_only` (`requireAggregateGeometry`,
`:720-780`). This is the #149 limitation, deferred for RC0.

Observed locally (macOS CPU build, 128 x 128 fixture): after a first run, a second run with `--only_do_unfinished`
changed nothing, and a third run adding `--dose_weighting --dose_per_frame 1.5` with the same `--o` also left the
output MRC untouched (same modification time). The consequence: **use a fresh `--o` whenever any processing option,
input, gain or defect file changes.** `run_dataset.py` and `run_multi_gpu.py` refuse an existing output directory for
the same reason.

Unchanged-settings resume, a representative failure, and non-prefix resume on a real dataset are part of the QF
campaign (`docs/release/RELEASE_CHECKLIST.md`) and are **UNRUN** here.

## 6. Failure behaviour that users will see

**This program does not roll back.** Product files are written directly to their destinations
(`submitImageWrite`, `src/motioncorr_runner.cpp:1530-1543`). When a write fails, the output writer cancels the remaining
queued writes and records the failure; it does not remove files that were already written
(`src/output_writer.cpp:102-133`, `src/motioncorr_runner.cpp:1547-1567`). The existing write-fault test resumes a
"truncated leftover" (`tests/test_write_faults.py:21-30`). Therefore a **failed movie** means: no completion STAR for it
and no entry in the joint outputs. It does **not** mean that no file for that movie exists, and **file presence alone is
not success.** After a failure you may find:

- a truncated destination MRC from the write that failed;
- earlier, complete MRC products of the same movie when a later product failed;
- an auxiliary `_PS.mrc` (item 1);
- a per-movie `.log` ending with an `ERROR:` line (`:1547-1567`).

The only case where this page promises that no aligned image was written is a failure before reconstruction
(for example a fatal CUDA error, item 4, which stops before any image is submitted). For everything else, take the
per-movie STAR (the resume completion marker, `:785-827`) together with a successful exit status as the success signal.

**Batches.** When any movie in a run fails, the run exits with an error that names the movies, retains the healthy
movies' per-movie products, and does **not** generate the joint output for the whole batch (`:1086-1092`: "Successful
per-movie outputs were retained; joint output was not generated."). Do not mistake the retained per-movie products of
healthy movies for a published dataset.

1. **`_PS.mrc` can survive a failed movie (inherited behaviour).** With `--grouping_for_ps`, the power spectrum is
   written early, before global alignment (`src/motioncorr_runner.cpp:3328`, output name set at `:2082`). Nothing
   removes it. If patch alignment then fails for the same movie, the movie is marked failed and its aligned products and
   joint outputs are withheld, but `<movie>_PS.mrc` remains. Source: R-SRC review on
   [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6223311256).
2. **A failed Ghostscript render is non-fatal in normal mode and strict in `--aggregate_only`.**
   - `header.pdf` and `batch.pdf`: a failed `gs` run prints "ERROR in executing: gs ..." and, in normal mode, an
     **empty placeholder PDF** is written (`src/CPlot2D.cpp:66-98`). Observed locally without `gs`.
   - `logfile.pdf`: in normal mode the placeholder is explicitly disabled and a failed render neither fails the job nor
     writes a placeholder (`src/motioncorr_runner.cpp:1835-1842`). Locally, without `gs`, a single-process run exited 0
     and wrote `header.pdf` and `batch.pdf` but no `logfile.pdf`.
   - With `--aggregate_only` (and therefore `run_dataset.py`) the same failure is an error (`CPlot2D.cpp:93`).
   - **Fix F1 is merged (#200, `ea86fc90`): a failed render leaves no `logfile.pdf`; strict in `--aggregate_only`.** A failed
     render now removes a partial or earlier regular file (`src/CPlot2D.cpp:30-36, 96`; `src/motioncorr_runner.cpp:1877-1882` for the
     concatenation route). `header.pdf` and `batch.pdf` still get the empty placeholder in normal mode. The absence of `logfile.pdf` therefore means
     "no report was produced", not a successful run; the numerical products are the MRC and STAR files.
3. A pinned `--ingest` that cannot be honoured fails the movie before any host decode (§2).
4. A fatal CUDA error refuses any CPU fallback and fails the movie (`src/motioncorr_runner.cpp:2259-2271`). A
   recoverable device-ingest failure re-reads the movie on the host and continues (`:2319-2324`). The fatal-path CUDA tests inject error
   codes; **genuine device poisoning is not tested** and is post-RC0 work (TST2, [#213](https://github.com/KingAlejandro/MotionCorr-standalone/issues/213)).
5. **Truncated or short raw MRC movies, gain references and defect maps fail closed (F3/F3b, D5; merged, #205 `f67a5866`).** The negative return of `Image::read` (short
   `fread` or seek failure) is now checked at every read, so a truncated movie no longer runs on unread memory. This is movie-level rejection (the criterion of
   `POST_FREEZE_TEST_PLAN.md` §4.1): exit 1, no completion STAR for the movie, no joint output for the batch. The named messages are:
   - movie frames: `Failed to read frame N (0-based) of FILE: the movie is truncated or unreadable.` (`src/motioncorr_runner.cpp:2466-2476`, all five read routes through one helper);
   - gain reference: `Failed to read the gain reference FILE: the file is truncated or unreadable.` (`:639-646, 2030-2037`; EER gain `src/renderEER.h:131`);
   - defect map: `Failed to read the defect map FILE: ...` (`:5155-5159`).
   A truncated gain or defect map fails **every** movie and the job (exit 1, no products); with `--gain_rot` the gain is read before any movie. Valid input is byte-identical to
   `1db86902` and the truncated cases fail on `1db86902` (PR #205; tests `TruncatedMrcMovie`, `TruncatedGainDefect` and their `Cuda` variants). This does **not** cover compressed
   MRC (item 6, F4) or EER frame reads, which are unchanged. Frozen-SHA rerun of the two required tests: pending RC0 QF.
6. **Compressed MRC (`.bz2`/`.xz`/`.zst`) integrity is not fully checked (F4, documented RC0 limitation, D5).** The decoder's exit status is not
   checked after a complete read (`src/image.h:1958-1963`, `pclose` result ignored, "exit status is not a complete-file integrity check
   here"), so some corruption that is reported only at the end of the stream (for example a missing final byte or a bad index CRC) is
   **accepted**. Short reads are still caught. **You must validate compressed inputs independently before processing**: `xz -t FILE`,
   `zstd -t FILE`, `bzip2 -t FILE` (or `pbzip2 -t FILE`). Scheduled fix: [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214).
7. **Big-endian mode-0 MRC with nx = 128 is not byte-swap detected** (F5). Observed on the tested GCC build: the movie failed identically on every
   tested route. The swap heuristic is `abs(header->mode) > SWAPTRIG || abs(header->nx) > SWAPTRIG` (`src/rwMRC.h:149`), and a byte-swapped
   nx of 128 is `INT_MIN`, for which `abs` is undefined behaviour, so **no portable clean failure is promised** on other compilers or platforms.
   Document-only for RC0 (W-MRC-Q, PR #204; R-QA1).

Auxiliary versus numerical products: the corrected MRC(s) and the per-movie and joint STAR files carry the
results. `logfile.pdf`, `header.pdf`, `batch.pdf`, the shift EPS plots, `.log` and `_PS.mrc` are auxiliary reports.

## 7. Optional dependencies

- **nvCOMP**: `-DUSE_NVCOMP=ON` (default OFF), needs `NVCOMP_ROOT`; not vendored (`CMakeLists.txt:140-153`). Tested with nvCOMP
  5.3.0.16 and CUDA 12.8 (PR #209). See "Optional proprietary dependencies" below.
- **Ghostscript** (`gs`): needed for `logfile.pdf`, `header.pdf` and `batch.pdf`. A single-process run without it still
  writes the MRC, STAR and EPS products, but the PDF reports are absent or empty (§6); `run_dataset.py` fails (§4).
- **pbzip2 / xz / zstd**: only for compressed MRC input (§2). The same tools (`xz -t`, `zstd -t`, `bzip2 -t`/`pbzip2 -t`) are needed to validate compressed inputs first (§6 item 6).
- **Python 3 with NumPy**: required at configure time when `BUILD_TESTING=ON` (`CMakeLists.txt:343-349`); the CMake
  configure fails with "BUILD_TESTING=ON requires Python 3 with 'numpy' installed." (reproduced locally). `README.md` now
  says so beside the build prerequisites. The tools under `tools/` also need NumPy.

### Optional proprietary dependencies (D2, interim policy A)

- **nvCOMP** (tested 5.3.0.16) is **optional and default OFF** (`USE_NVCOMP`), is **not included or vendored** in this repository, and is
  licensed under NVIDIA's SDK agreement, which the user obtains and accepts from NVIDIA.
- **The project distributes no binaries linked against nvCOMP or nvTIFF.**
- Redistribution of such binaries remains subject to licensing review. Anyone who builds and distributes a binary linked against nvCOMP
  (or nvTIFF) must review both licences first.
- **nvTIFF is not used by RC0.**

Basis: maintainer decision D2 on #198 and the decision record [`docs/rc0/decoder_trust_and_dependencies.md`](../rc0/decoder_trust_and_dependencies.md) §3 (merged, #199 `a1ab83f2`).
This page makes no legal claim beyond these statements.

### Decoder trust boundary (D1, option 1: trusted-input precondition; no code change)

On builds configured with `-DUSE_NVCOMP=ON` (default OFF), `--ingest auto` sends **eligible TIFFs** (16-bit, Deflate or Adobe-Deflate, one row per
strip, no predictor, native byte order; full list in §2) to NVIDIA nvCOMP's GPU Deflate decoder. nvCOMP 5.3 documents **undefined behaviour for
corrupt compressed input** (`nvcompBatchedDeflateDecompressAsync`; #134, record [`docs/rc0/decoder_trust_and_dependencies.md`](../rc0/decoder_trust_and_dependencies.md) §4). MotionCorr checks the TIFF structure, the zlib wrapper,
sizes and offsets, the decoder status, the decoded length and an Adler-32 checksum before it uses any decoded data, but it **cannot guarantee safe
behaviour on a corrupt Deflate body**. This route therefore **assumes complete, unmodified acquisition files**. **Use `--ingest compact` for
files of unknown integrity or files that are still being written.**

Two further statements: a file that changes **between the tag scan and the strip read is not detected** (follow-up
[#215](https://github.com/KingAlejandro/MotionCorr-standalone/issues/215), post-RC0), and **checked arithmetic on the pre-decode offset/size path is in force
(T3, #217 merged `483e881d`)**: an overflow or an unreadable strip offset becomes a named decline (§2). The trusted-input precondition for the Deflate body is unchanged.

## 8. Known limitations

- **The `0.001` relative-RMSE diagnostic fails for CUDA versus CPU.** On the 24 tutorial movies CUDA versus fixed CPU
  `--j 1` gives relative RMSE 0.002899-0.010082 against 0.001 (0/24 pass the relaxed profile; every other relaxed check
  passes). The explicit `--gate backend` profile records this as a non-blocking diagnostic. This is a strict CPU-agreement
  measurement, not a statement about scientific validity. `docs/gate_contract.md` §3, §7;
  `docs/cuda_global_alignment_validation.md`; `docs/cuda_24_movies_gate2_rerun.json`. These are historical results and do not
  describe the RC0 composition.
- **S1 (PROVISIONAL): CPU and CUDA local alignment differ substantially on some movies.** See §0 for the full statement; it is the first
  priority of the post-freeze campaign.
- **Backend-gate absolute limits do not transfer across intensity scales.** The absolute RMSE (0.020) and max-pixel (5) limits of `--gate backend`
  failed in 9 and 5 of 14 CPU-versus-CUDA cases at `1db86902`, tracking image intensity (for example EMPIAR-10028, sigma about 430); the gate contract
  notes absolute limits are not portable (`docs/gate_contract.md` §4.2). Config-G relative RMSE CPU versus CUDA was 0.0015-0.023 on the seven corpus
  families tested (PR #209). Limits are unchanged.
- **EER-MS (new):** malformed-EER memory safety is not established; EER inputs are assumed complete and unmodified (§2).
- **There is no Tier D scientific gate.** No CTF/FSC/B-factor non-inferiority result exists for CPU, CUDA or hybrid output
  (`docs/gate_contract.md` §1; #61, #73 open). RC0 is an evaluation release.
- Tier A (byte-exact CPU regression) and Tier C (known-motion truth) exist and are enforced
  (`docs/gate_contract.md` §1). The CUDA output is not byte-identical to CPU output.
- Standalone versus RELION 5.1: 1/24 byte-identical movies at `--j 1` (#20 open). Same-backend determinism across `--j`
  holds for the CPU build (`docs/gate_contract.md` §7).
- `--max_iter 5` non-convergence: 41 of 50 patches in EMPIAR-10641 and 30 of 50 in EMPIAR-10216 did not converge in the
  #186 pass; those movies spend most of their time in the retry (`docs/workload_corpus/gpu/README.md`). Data dependent.
- Resume (§5). Multi-GPU is process-per-device only (§4).
- **GPU memory: free-VRAM floors per geometry, the streaming fallback and a non-monotone gap: see "GPU memory (QM)" at the end of this section.** Binning is not a memory workaround on the strength of this page: early binning skips the resident session (`:2278`) and does the global FFT on the CPU, changes the output sampling, and the later CUDA stages' memory behaviour is unqualified.
- **Host RAM with `--grouping_for_ps` on CUDA:** one extra Fourier movie on the host (§3).
- The `ProfilingKit` test has a 30 s subprocess timeout (`tools/profiling/tests/test_import_subset_boundaries.py`) that is load sensitive; it
  failed once under host load about 27 in the Linux CPU qualification and passed on rerun (PR #209). Run CTest on a quiet host, or record it.
- Resident retry (#197), 10641: host RSS 2.07 GiB with the resident retry versus 7.0 GiB before #197; one resident retry allocates 504 MiB of
  VRAM (301 MiB on 10216) (PR #207, single runs).
- **macOS arm64: builds and runs; not qualified; known CPU CTest differences.** The macOS CPU suite has two failures and one skip (68 collected, 65 passed at the merge with
  `483e881d`; the same two failed on `1db86902`):
  - `SyntheticRegression` fails because **libc `rand()` differs from glibc**: hot-pixel and defect replacement draw positions and values from `rand()` seeded by `--seed`, so the same `--seed` gives
    different replacements, and therefore different output bytes, on macOS and on glibc Linux (about 391 replaced pixels in that fixture; maximum pixel difference 23.65). Outputs are **not bit-identical across C
    libraries for the same `--seed`**; behaviour on Linux is unchanged. Documented only for RC0; post-RC0 options (a portable project-owned RNG, per-platform references, restricting the bit-exact assertion to glibc)
    are the maintainer's decision ([#222](https://github.com/KingAlejandro/MotionCorr-standalone/issues/222); W-MAC on #198). No numerical gate is relaxed.
  - `MultiGpuScheduling` fails from a **test-harness issue**: the tomography endpoint test compares paths through the macOS `/var` symlink. [PR #223](https://github.com/KingAlejandro/MotionCorr-standalone/pull/223)
    fixes the test (**PENDING MERGE**); **whether #223 is in the frozen SHA is a freeze-time placeholder**.
  - `NativeMovieStaging` is Linux-only and is skipped.
  No unqualified "macOS supported" statement is made anywhere in these documents. Section 3 of `docs/release/RELEASE_CHECKLIST.md`.
- `python3 tools/multi_gpu/run_dataset.py` emits a `SyntaxWarning: 'return' in a 'finally' block` on Python 3.14
  (`run_dataset.py:172`). Cosmetic as of this draft.

### GPU memory (QM)

Evidence: [PR #225](https://github.com/KingAlejandro/MotionCorr-standalone/pull/225) (`docs/rc0/qual_qm_vram/` on that branch, main `483e881d`): 162 runs on one A100 80 GB with a VRAM balloon, 0 crashes, 0 hangs, 0 wrong outputs;
every completed constrained run was identical to its unconstrained run and every failure was clean (no products written). Audited by R-QM
([audit](https://github.com/KingAlejandro/MotionCorr-standalone/pull/225#issuecomment-6234250216)). The three defects it found (D1 stale CUDA error, D2 config-L admission gap, D3 late OOM failure) are post-RC0
([#226](https://github.com/KingAlejandro/MotionCorr-standalone/issues/226)); none changes output. The wording below is R-QM's, not the worker's first draft.

> **GPU memory.** The resident CUDA route keeps the movie on the device twice (real space and Fourier space, about 8 bytes × pixels × frames) plus 0.7–4.2 GiB of workspace. The table gives the minimum **free GPU memory at launch** (`nvidia-smi` free memory before `motioncorr` creates its ~0.4 GiB CUDA context, not nominal card size) for the full-speed route, measured with `--use_own --gpu 0 --j 8` on one A100 80 GB card using a VRAM balloon (one movie per family; leave 1–2 GiB of margin):
>
> | Movie | Full speed (global / patch) | Slower streaming route completes | Fails |
> |---|---|---|---|
> | 3838×3710×24 (Deflate TIFF, nvCOMP) | 4 / 4 GiB | 2–3 GiB | ≤ 1 GiB |
> | 4096²×59 (int16 MRC, compact) | 8.25 / 8.75 GiB | 5–7.5 GiB | ≤ 4 GiB |
> | 4096²×144 (Falcon 4 EER, compact) | 19 / 20 GiB | 12–18.5 GiB | ≤ 11 GiB |
> | 11520×8184×50 (K3-class u8 TIFF, compact) | 37.5 / 39 GiB | 22–36.5 GiB | ≤ 21 GiB |
>
> Below the resident session threshold, the movie falls back to the streaming route (identical output, 3–9× slower, and several times the host RAM: about 36 GiB RSS for 11520×8184×50, 21 GiB for 4096²×144, and 7.7 GiB for 4096²×59; hosts with insufficient RAM are untested). Below the streaming floor, the movie fails cleanly after host preprocessing with an out-of-memory error and writes no products. **Completion is not monotone in free VRAM:** in the ~0.5–1.5 GiB band **between the streaming range and the full-speed floor** (8.0–8.5, 19–19.5, and 37.0–38.5 GiB above), the resident session is admitted before gain/sum or patch-stage buffers are allocated, so global alignment falls back to CPU preprocessing (8.0 and 37.0 GiB) and local (patch) alignment **fails** with a patch-stage out-of-memory error (8.5, 19–19.5, and 37.5–38.5 GiB) even though lower free VRAM completes via streaming (#226 D2). Do not size runs in that gap or right at the floor. After a movie fails with a device out-of-memory error in a multi-movie run, a stale CUDA error makes the next movie in the same process fall back one route step under `--ingest auto` (identical output, slower route; under a pinned `--ingest nvcomp`, that next movie will be refused; #226 D1). `--ingest compact` refuses immediately (~1 s, no products) when the resident session cannot be created. Not covered here: `--eer_upsampling 2` (see §2), `--grouping_for_ps` (+1 Fourier movie in host RAM, §3), `--bin_factor`, float32 MRC, and real smaller GPUs (whose driver reservation may differ from the 80 GB A100).

Caveats that stay with the table: the floors are **free GiB at launch measured with a VRAM balloon on one A100 80 GB, not nominal card sizes**; card-size conclusions are estimates and were not
measured (the 80 GB card's driver reserve was 766 MiB; a small card's may differ); one movie per family, bracketed at 1 GiB / 0.5 GiB steps (NVML sampling is a lower bound), and the e10361 floor was
not bisected; host-RAM exhaustion (hosts below about 36 GiB for 11520×8184×50) is untested; multi-GPU, `e10028`, `e10164` and `e10641` were not run (PR #225 README limitations, R-QM section 4). The QM
status in the qualification lists is **completed (pre-freeze, on `483e881d`), with these documented limits**.

## 9. CPU dose-weighting symmetry (#220): qualified-toolchain contract (PENDING MERGE)

**Status: PENDING MERGE.** [PR #220](https://github.com/KingAlejandro/MotionCorr-standalone/pull/220) (a lean port of #179, register item C5) is expected to merge
before the freeze; this section describes the contract it implements and must be re-checked against the merged source. The maintainer decided it is **acceptable for RC0 under an
explicit qualified-toolchain contract, not as a universal portability claim**.

- **Default.** The symmetric-row optimisation of the CPU `doseWeighting` is enabled **by default only on x86-64 GCC without FMA code generation** (the configuration that was
  measured). Elsewhere the original code runs. The selection is the CMake setting `MOTIONCORR_CPU_DOSE_SYMMETRY` (OFF, ON or AUTO; AUTO is the default) read by
  `src/cpu_dose_symmetry_mode.h` on PR #220's branch.
- **Other toolchains.** A site may set `MOTIONCORR_CPU_DOSE_SYMMETRY=ON` **only after `CpuDoseSymmetry` passes on its own toolchain**. The test compares exact complex bits
  against the frozen base (1,681 cases at PR #220's head), so a contraction or vectorisation difference fails CTest instead of passing silently.
- **Not qualified, not recommended:** native FMA flags (`-march=native`, `-mfma`, x86-64-v3) and compilers that PR #220 lists as UNRUN (Linux aarch64 GCC, PowerPC,
  NVHPC and Intel compilers).
- **Performance claim: x86-64 cpu64 only.** The measured whole-job reduction is 3-4 % (tutorial -3.28 %, EMPIAR-10474 Falcon 4 -3.97 %, resolved beyond the null; EMPIAR-10216
  unresolved; products identical) from the paired comparison in [PR #218](https://github.com/KingAlejandro/MotionCorr-standalone/pull/218) and the evaluation on
  [#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6228524546). It is not a claim for any other platform.
- **Required in release qualification:** `CpuDoseSymmetry` is added to the required tests (PR #220 puts it in `tools/validate_test_collection.py`), so QF must run it on the
  frozen SHA. Frozen-SHA result: pending RC0 QF.

## 10. Deployment note: huge pages (#188)

On hosts where `/sys/kernel/mm/transparent_hugepage/enabled` is `madvise`, start the process with
`GLIBC_TUNABLES=glibc.malloc.hugetlb=1` (glibc 2.35 or later). On unmodified main the cpu64 24-movie CPU batch went from
508 s to 392 s (4 alternating rounds, one host) with identical output (`docs/host_buffer_reuse.md`;
`docs/issue10_allocator_control/`). THP `always` (SCARF) and `never` were not measured, and no gain is expected on
`always`. The binary prints the host THP mode and any `GLIBC_TUNABLES` on its `Host allocator:` line; record it with any
timing, because timings across hosts with different THP settings are not comparable. The tunable is a deployment setting
and is not set by the program. Qualification: pending RC0 QF.

## 11. Where the evidence lives

`docs/gate_contract.md` (what each gate means), `docs/spa_24_movies_validation.md` (24-movie CPU/RELION comparison),
`docs/cuda_global_alignment_validation.md` (historical CUDA report), `docs/known_motion_validation.md`,
`docs/workload_corpus/` (#186 baselines), `docs/multi_gpu/`, `docs/release/RC0_ACCEPTANCE_REPORT.md` (results of the
frozen-SHA qualification, to be filled).
