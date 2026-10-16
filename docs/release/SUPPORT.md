# MotionCorr RC0 support page (DRAFT)

> **This is an EVALUATION RC0, not a stable release** (maintainer decision D7,
> [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198)). It is offered for evaluation and heavy testing.
> No unrestricted or stable support is claimed for CUDA local alignment (see **S1** below), and no scientific equivalence or
> preference for either backend is established.

Status: **draft for RC0, pre-freeze, revision 2** (after the R-REL accuracy review of PR #201 and the maintainer decisions D1, D2,
T3, D5, D6 and D7). Written against main `2b3c74b3` (the merge of #200 F1 and #210 TST1 on top of `1db86902`); the qualification
evidence cited below was gathered at `1db86902`. Source line numbers are at `2b3c74b3` and will move; re-check them against the
frozen SHA. Every **Qualification** cell says **pending RC0 QF** (the full CPU + native CUDA qualification of the frozen SHA, register
item QF in #198), unless a row cites evidence. Linux/CUDA command validation by this document's author is **UNRUN**; the qualification
lanes on #198 (PRs #204, #207, #208, #209, #212) are cited as evidence, not re-run here.

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
| nvCOMP GPU Deflate ingest | n/a | only with `-DUSE_NVCOMP=ON` (default OFF); trusted-input precondition, §7 | Decided (D1 option 1, D2 interim policy A) |
| Truncated or short raw MRC movie, gain reference, defect map | read errors ignored; products published from partly unread memory | the movie fails explicitly (a truncated gain fails every movie) | Decided (D5); **lands with PR #205, pending**, §6 item 5 |
| Frame-count checking | not checked | `--expected_frames` and the per-movie STAR counts `rlnNrOfFrames` / `rlnTomoTiltMovieFrameCount` are compared with the **decoded** frame count; a mismatch fails the movie (`:454-478, 2141-2146`) | Verified |
| `--only_do_unfinished` | skips a movie whose output micrograph file exists | re-processes unless the products are complete (`isMovieComplete`, §5); a changed-settings resume is still not detected (#149), as in RELION | Verified |
| Pinned ingest, `--aggregate_only` | n/a | `--ingest nvcomp/compact/float` refuses a movie that cannot use that route; `--aggregate_only` is new and strict | Verified |
| `logfile.pdf` after a failed Ghostscript render | sub-reports get empty placeholders; `logfile.pdf` is built by concatenation | normal mode leaves **no** `logfile.pdf` (F1, #200 merged); `--aggregate_only` fails strictly, §6 | Verified for the standalone |
| Worker reports; failed movie | per-movie files may remain | `--skip_report_pdf` for multi-GPU workers; no rollback: partial or earlier per-movie files and an early `_PS.mrc` can remain, joint outputs withheld, §6 | Verified |
| Corrupt EER fractions | skipped with a warning (inherited) | preserved: wrong-pixel-count fractions are skipped and the movie publishes; supply `--expected_frames`, §2 | Decided (D6) |
| Compressed MRC integrity | decompressor exit status not checked (inherited) | unchanged; validate inputs with `xz -t`/`zstd -t`/`bzip2 -t`, §6 item 6 | Decided (D5/F4, fix #214) |
| MRC mode 0, early binning, dose-weighting voltages | mode 0 read as signed int8; early binning on by default when `--bin_factor` is not 1; dose weighting only at 100/200/300 kV | unchanged; early binning also bypasses the GPU-resident path (§2, §3) | Verified |
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
| Supported (intended) | `--use_own` on CPU, Release build, Linux x86_64 and macOS arm64 | CPU CTest suite; `README.md` build section | pending RC0 QF |
| Supported for evaluation | `--use_own --gpu <one id>` on a CUDA build (`-DCUDA=ON`), one process per device. **Local alignment: no unrestricted or stable claim, see S1** | `src/motioncorr_runner.cpp:342-405`; qualification PRs #204, #207, #208, #209 | same-backend contracts qualified at `1db86902` (#209); frozen SHA pending RC0 QF |
| Supported for evaluation | Several GPUs through `tools/multi_gpu/run_dataset.py` (one process per device) | §4; `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`; PR #209 | 1/2/4 workers x 24 tutorial movies passed at `1db86902` including a real-Ghostscript `logfile.pdf` (#209); frozen SHA pending RC0 QF |
| Experimental | nvCOMP device Deflate ingest (`-DUSE_NVCOMP=ON`, default OFF); assumes complete, unmodified input files, §7 | `CMakeLists.txt:140`; D1 (option 1), D2 (interim policy A) | qualified for route invariance at `1db86902` (#209); frozen SHA pending RC0 QF |
| Experimental | `--interpolate_shifts` | help text: "(EXPERIMENTAL)", `src/motioncorr_runner.cpp:212` | pending RC0 QF |
| Not qualified | Every option or input not named in §2 and §3 | no evidence on this page | n/a |
| Unsupported | `--gpu` with a device list under `--use_own` | rejected, `src/motioncorr_runner.cpp:342-370` | refusal verified locally on a CPU build only, §4 |
| Unsupported | `--use_motioncor2` (needs the external MotionCor2 executable) | not part of this program; `src/motioncorr_runner.cpp:222` | n/a |
| Unsupported | One process driving several GPUs (#175), MPI | #175 is parked; `src/motioncorr_runner.cpp:362-367` says the repository has no MPI runner | n/a |
| Unsupported | Resume with changed processing settings in the same `--o` (#149 deferred), §5 | #149 | n/a |
| Not in RC0 (NO-GO) | nvTIFF/LZW device route (#141/#152): **not used by RC0** | #198 register L1: NO-GO for RC0 | n/a |
| Not in RC0 (NO-GO, parked) | nvCOMP Deflate widening to 8-bit samples and any rows-per-strip (#138), parked as [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206) | #198 register T1: NO-GO for RC0; reopen after RC0 only with a real deposited u8/multi-row Deflate dataset, a strips-per-frame admission floor and D1 | n/a |
| Not merged, bounded experiment (not in RC0) | device EER renderer (#193 option 2); #179, #181, #183 CPU optimisations | #198 register E2 (integration NO-GO for RC0 unless all gates pass before freeze) and C5-C7 (bounded under the amended rule, [#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6223528151); not in RC0 unless they pass it) | n/a |

CUDA architecture: `CMakeLists.txt:118-119` defaults `CMAKE_CUDA_ARCHITECTURES` to 80 unless the user or
`CUDAARCHS` sets it. An sm80 binary is not a statement that other devices work.

## 2. Input capability matrix (from current source)

Routes: **CPU** = `--use_own` without CUDA, host reader into float frames. **CUDA float** = host decodes to a float
movie, device does the rest. **CUDA compact** = host decodes into the file's native integer type, the device expands
to float and applies gain. **CUDA nvCOMP** = Deflate strips are decompressed on the device
(`USE_NVCOMP=ON` build only).

`--ingest_witness FILE` appends one line `<movie path> <value>`, `<value>` being `nvcomp`, `compact` or `float`
(`src/motioncorr_runner.cpp:2428-2441`). It writes nothing else. It records the route **selected** for a movie that
reached that point; it is not a record of completion or success:

- a movie skipped by resume is filtered earlier and has no line (`:559-565`);
- a pinned `--ingest` that cannot be honoured fails before the line is appended (`:2318-2322, 2415-2436`), so a
  refusal has no line of its own (use a positive control to prove the intended route);
- compact and float lines are written before the host decode (`:2428-2446`), so a movie that is damaged and then fails
  to decode can still have a line.

On a CPU-only build, and on a CUDA build with no resident CUDA session, the value is `float`. **Early binning** (`--bin_factor` other
than 1 turns it on by default) bypasses the resident session and the compact staging (`:2269`, `:2374`), so such a movie always takes the
float route; late binning needs `--no_early_binning`. Session-initialisation failure also gives `float`.

| Input | Sample type | Compression | CPU | CUDA float | CUDA compact | CUDA nvCOMP | Witness on CUDA, `--ingest auto` | Source | Qualification |
|---|---|---|---|---|---|---|---|---|---|
| TIFF | uint16 | Deflate (8 or 32946) that meets **every** nvCOMP admission test listed below the table | yes | yes (`--ingest float`) | yes (`:2368`) | **yes**, with a live resident session and a successful ingest | `nvcomp` (nvCOMP build) else `compact` | `src/acc/cuda/cuda_movie_session.cu:1420-1463` | pending RC0 QF |
| TIFF | uint16 | Deflate that fails any admission test, or whose ingest declines for budget or arena reasons | yes | yes | yes | declines and logs "nvCOMP ingestion declined (...); using the host reader." (`cuda_movie_session.cu:1479`; budget refusals `:1562, 1679`) | `compact` | same | pending RC0 QF |
| TIFF | uint16 | any other codec LibTIFF decodes (LZW, none, ...) | yes | yes | yes | no (not Deflate) | `compact` | `:2368-2369`; `cuda_movie_session.cu:1448-1449` | pending RC0 QF |
| TIFF | uint8 | any LibTIFF codec | yes | yes | yes | no: requires 16 bits, `cuda_movie_session.cu:1445` | `compact` | `:2368-2369` | pending RC0 QF |
| TIFF | int8, int16 (signed samples) | any | yes | yes | **no**: signed TIFF is read as `SChar`/`SShort`, which the compact TIFF test excludes (`:2368-2369`) | no (also fails the nvCOMP unsigned-sample test) | `float` | `src/rwTIFF.h:119-129` | pending RC0 QF |
| TIFF | float32 | any | yes | yes | no | no | `float` | `src/rwTIFF.h:131` | pending RC0 QF |
| TIFF | 4-bit packed (K2/K3 special case, 8-bit TIFF of K3 super-resolution dimensions) | any | yes | yes | no | no | `float` | `src/rwTIFF.h:100-113` | pending RC0 QF |
| MRC / MRCS | mode 6 (uint16) | none | yes | yes | yes | n/a | `compact` | `src/rwMRC.h:213`; `:2370-2372` | pending RC0 QF |
| MRC / MRCS | mode 1 (int16), mode 0 (**int8, signed**) | none | yes | yes | yes, staged in the signed type (#195) | n/a | `compact` | `src/rwMRC.h:200-205`; `:2370-2372, 2391-2413` | pending RC0 QF |
| MRC / MRCS | mode 2 (float32), mode 12 (float16), mode 101 (4-bit) | none | yes | yes | no | n/a | `float` | `src/rwMRC.h:206, 216-227` | pending RC0 QF |
| MRC / MRCS | modes 3, 4 (complex); any other mode | none | refused at read | refused | refused | n/a | n/a | `src/rwMRC.h:209-228` | pending RC0 QF |
| `.mrc/.mrcs` + `.bz2`/`.xz`/`.zst` | per header | external `pbzip2`, `xz` or `zstd` must be on `PATH`. One sequential frame reader (`:2454`); only `pbzip2` takes a thread count (`-cdkp<N>`, N = the IO-thread setting, `:2131`), `xz -cdk` and `zstd -cdk` take none | yes | yes | **no** (excluded from compact and nvCOMP) | no | `float` | `src/image.h:1814-1851, 1886-1897`; `src/motioncorr_runner.cpp:2289, 2374, 2454` | pending RC0 QF |
| EER | counts, rendered on the host; square 2048 x 2048 or 4096 x 4096 only | EER | yes (float movie) | yes | **yes**, only if `eer_grouping` x (4 if `--eer_upsampling -1`, else 1) <= 65535, rendered into uint16 (#196) | n/a | `compact`, otherwise `float` (logged: "can exceed 65535 counts per pixel; using the float movie") | `:2348-2363`; `src/renderEER.cpp:150-155, 193-195, 232-236` | pending RC0 QF |

Shape and format restrictions the cells above do not repeat:

- **MRC mode 101 (4-bit)** is refused when both nx and ny are odd (`src/rwMRC.h:219-225`).
- **EER upsampling.** The program accepts `-1`, `1`, `2` and `3` on a 4096 x 4096 detector (`src/renderEER.cpp:150-155`); the option
  help says "1 or 2". A 2048 x 2048 movie, and a movie with the 2-bit sub-pixel encoding (compression tag 65002), take only 1 and 2
  (`:219-236, 573-593`). A TIFF-wrapped EER whose first page is a sum (the TIA variant) is not supported (`:193-195`).
- **EER corpus coverage.** All seven corpus EER files are encoding 65001 at 4096 x 4096. Encodings 65000 and 65002 and the 2K
  detector were exercised only with **synthetic** movies; no real 65000, 65002 or 2K file was run (W-EER-Q, [PR #208](https://github.com/KingAlejandro/MotionCorr-standalone/pull/208)
  and #198 log).
- **EER frame count.** Trailing fractions are dropped: the frame count is `fractions / eer_grouping` with integer
  division (`src/motioncorr_runner.cpp:2125-2127`). This differs from `--group_frames`, which gives a non-dividing remainder to the
  **last** groups (`:2176-2186`).
- **EER corruption and missing frames (D6, inherited RELION behaviour).** A fraction whose decoded pixel count is wrong is skipped
  with a WARNING and **the movie still publishes** (`src/renderEER.cpp:564-567`, "This frame is skipped"). Two limits follow:
  - **undetected corruption:** corruption that leaves the pixel count right is not detected at all;
  - **missing frames:** a truncated EER file is processed as a shorter movie unless `--expected_frames` or a per-movie STAR frame count
    is supplied. **Supply one** for every EER dataset (`--expected_frames` is the grouped frame count). With either, a short movie fails.
  Preserved unchanged for RC0 by maintainer decision D6; identical before and after #196 and on both routes (#198 register E-1).
- **EER defect replacement** on the compact EER route uses the host path (`Iframes_u16` x gain); the sparse device gather is reachable only with
  nvCOMP input (PR #208).
- **EER memory (single runs per arm, PR #208, A100 80 GB, main `1db86902`).** `--eer_upsampling 2` doubles both dimensions
  (`src/renderEER.cpp:356-375`), so every movie buffer is four times larger (upsampling 3: sixteen times). Host RSS with the compact route
  was 34-39 % lower than the float route at upsampling 1 and 43-47 % lower at 2 and 3; there was no saving at -1 (not investigated). Device
  memory is unchanged, because the resident device buffers are float whatever the host staging type. A 144-group Falcon 4 movie at
  upsampling 2 **fit at 79,522 MiB** on the 80 GB card (calculated 80,520 MiB), with host RSS 21,547 MiB (compact) versus 40,171 MiB (float).
  There is essentially **no headroom**: upsampling 2 on large EER movies is unqualified on any card below 80 GB and marginal on 80 GB. The
  earlier #186 estimate was about 75 GiB, not run (`docs/workload_corpus/gpu/README.md`); the measurement above supersedes it.

Corpus labels (corrected in this PR, `docs/workload_corpus/corpus.md` and `families.json`):

- **The RELION tutorial movies are 16-bit Adobe-Deflate TIFF, RowsPerStrip 1, no predictor, unsigned integer samples, little-endian,
  width 3710 x height 3838** (W-TIFF, `tiffinfo`, [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206)); sample values are at
  most 68. This agrees with the nvCOMP admission rule (16 bits, one row per strip) and with the #186 witness `nvcomp`. The earlier label
  "u8 Deflate TIFF" and the 3838 x 3710 order were wrong.
- **EMPIAR-10164 is MRC mode 0, which this program reads as signed int8** (`src/rwMRC.h:200-202`); the maximum byte value in the corpus
  movies is 90, so no value changes under signed reading (W-MRC-Q, [PR #204](https://github.com/KingAlejandro/MotionCorr-standalone/pull/204)).
- The #186 GPU table (main `116eb04a`) records `float` for every MRC family. #195 (merged `faf5fbdf`) added the raw
  integer MRC compact route; PR #204 and #209 witness `compact` for modes 0 and 1 and `float` for float32 MRC. The matrix follows current source.

Positive nvCOMP admission tests (all must hold for every selected frame; any failure declines to the host reader, and
under a pinned `--ingest nvcomp` fails the movie), `src/acc/cuda/cuda_movie_session.cu:1420-1463`:

| Test | Line |
|---|---|
| native byte order | 1420 |
| no predictor (`TIFFTAG_PREDICTOR` = 1) | 1439 |
| unsigned integer samples | 1442 |
| fill order most-significant-bit first | 1443 |
| width and height equal the movie's, for every selected frame | 1444 |
| 16 bits per sample, one sample per pixel, contiguous planar layout | 1445-1447 |
| Deflate or Adobe Deflate compression | 1448-1449 |
| one full row per strip (strip count = ny, strip size = nx x 2 bytes) | 1453-1456 |
| per-strip compressed size of at least 7 bytes and below 4 GiB | 1463 |

A matching file can still decline later on pinned-memory, arena or chunk budgets (`:1562, 1679`; the pinned cap is
`MOTIONCORR_NVCOMP_PINNED_MAX_MB`, default 256 MiB per worker, `:1544-1553`). The witness is `nvcomp` only after a
successful ingest.

### Pinned `--ingest` semantics

`--ingest auto|nvcomp|compact|float` (default `auto`, `src/motioncorr_runner.cpp:157-163`). Valid only with
`--use_own` (`:236`). Any value other than `auto` makes a movie that cannot take that route **fail**, instead of
silently taking another (option help, `:157`).

| Value | Behaviour | Source |
|---|---|---|
| `auto` | nvCOMP if admitted, else compact if admitted, else float | `:2324-2327` |
| `nvcomp` | refused at start-up on a CPU-only build (`:244-245`) and on a CUDA build without `USE_NVCOMP=ON` (`:248-249`). Per movie: error if the device ingest did not run (`:2318-2322`) | as cited |
| `compact` | refused at start-up on a CPU-only build (`:244-245`). Per movie: error if no resident session or the movie is not an eligible type (`:2415-2421`) | as cited |
| `float` | always accepted; disables nvCOMP and compact | `:2288, 2354, 2373` |

Verified locally on a macOS CPU-only Release build (exit status 1 for each refusal): `--ingest compact` and
`--ingest nvcomp` (error at line 245), `--ingest bogus` (line 163); `--ingest float` and `--ingest auto` exit 0, and the
witness for the 128 x 128 MRCS fixture reads `float`. The per-movie refusals need a CUDA build and are **UNRUN**.

## 3. Option matrix

"Source" cites where the option is parsed or where behaviour changes. The CPU column describes the code, not a
qualification. The CUDA column says only what source shows; "not claimed" means this page has no evidence either way.

| Option | CPU | CUDA (`--gpu`) | Source | Qualification |
|---|---|---|---|---|
| Global alignment only (`--patch_x 1 --patch_y 1`, default) | yes | yes, device alignment (resident Fourier frames) | parse `:187-188`; execution `:3324-3330` | pending RC0 QF |
| Local patches (`--patch_x N --patch_y M`) | yes; a value of exactly 2 prints "too small ... Patch based alignment will be skipped" (`:308-314`) | yes, device patch alignment (`:3529-3538`) with resident retry for non-converged patches (#197) | as cited | pending RC0 QF |
| Dose weighting (`--dose_weighting`, `--angpix`, `--voltage`, `--dose_per_frame`, `--preexposure`) | yes; **voltage must be within 2 kV of 100, 200 or 300** or the movie fails | yes, in VRAM when a session is resident; CPU fallback exists | `:4075-4088, 4102` | pending RC0 QF |
| `--save_noDW` | yes (streamed unweighted sum, #178); **needs `--dose_weighting`**: without dose weighting the unweighted sum is the main `.mrc` and no `_noDW.mrc` is written | yes; the CUDA-to-CPU unweighted fallback has **not** been executed natively | `:3360` (`pre_dw_sum_needed`), `:4048-4054`, resume `:789`; #198 item C1 | pending RC0 QF |
| `--even_odd_split` (`_EVN.mrc`, `_ODD.mrc`) | yes | yes | `:3360, 3962-3970` | pending RC0 QF |
| `--bin_factor` (non-integer allowed) | yes; early binning is on by default when binning; **the binned dimensions must both be even** or the movie fails | early binning (the default when binning) skips the resident session and compact staging, so the movie takes the float route and the global FFT stays on the CPU; late binning needs `--no_early_binning`. Route-invariance of late/early binning was checked on valid input (PR #204) | `:182, 217-219, 2269, 2374, 3116-3120, 3146-3152`; late binning `:4954-4956` | pending RC0 QF |
| `--group_frames N` | yes; fewer than 3 groups after grouping skips the movie; a non-dividing remainder goes to the **last** groups (`:2176-2186`) | identical across routes for `--group_frames 4` (PR #207) | `:2165-2186` | pending RC0 QF |
| `--eer_grouping`, `--eer_upsampling` | yes; see §2 for accepted values, shapes and the trailing-fraction rule | compact route only within the uint16 limit; **upsampling 2 quadruples the movie storage: a 144-group Falcon 4 movie fit at 79,522 MiB on an 80 GB card, no headroom** (§2, PR #208) | `:2348-2363` | pending RC0 QF |
| Gain (`--gainref`, `--gain_rot`, `--gain_flip`) | yes; size must match the movie or the movie fails | yes; device gain applied on the compact and nvCOMP routes | `:2208-2221` | pending RC0 QF |
| Defect file (`--defect_file`; `--skip_defect`; `--seed`) | yes; a SerialEM-format `.txt` is rejected. `--skip_defect` skips **both** the automatic hot-pixel detection and the correction with the supplied defect mask (both sit inside `if (!skip_defect)`) | replacement neighbours are read from the typed host staging on the compact routes (`:3024-3039`) and uploaded as sparse replacements; the sparse **device** gather (`gatherFrameSamples`) is used only for nvCOMP input, which has no host frames (`:2949-2963, 3062-3069`) | `:190, 267-272, 2727, 2834`; `cuda_movie_session.cu:1258` | pending RC0 QF |
| `--first_frame_sum`, `--last_frame_sum` | yes; frames outside the range are not used at all | not claimed | `:2152-2160` | pending RC0 QF |
| `--grouping_for_ps`, `--ps_size` (`_PS.mrc`) | yes | **on the resident CUDA path this downloads the whole Fourier movie to the host** (`:3210-3217`): about one complex movie of extra host RAM. Measured on EMPIAR-10216 with `--grouping_for_ps 4` (single samples, PR #204): about **+3.8 GiB** on the float route and about **+1.9 GiB** on the compact route | `:3208-3311`; failure behaviour, §6 | pending RC0 QF |
| `--float16` | yes, requires `--grouping_for_ps > 0` | not claimed | `:205, 225-226` | pending RC0 QF |
| `--expected_frames` | yes; a different decoded frame count fails the movie. It is a **fallback**: a per-movie STAR frame count overrides it | same | `:173, 1013-1021, 2141-2146` | pending RC0 QF |
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
  24 tutorial movies, configs G and L, 6/6 dataset-endpoint PASS; workers on distinct, witnessed GPU UUIDs; products identical across worker counts
  and to a single process; joint STAR and a 30-page `logfile.pdf` rendered with real Ghostscript 10.02.1. A mixed tutorial + 10641 + EER 2-worker run was identical to
  a 1-worker run. Not run: 10441 and 10641 config G/L alone, launcher failure/resume injection, PDF page content comparison, real
  out-of-memory, a second venue, timing. Re-verification on the frozen SHA is pending RC0 QF.
- Earlier scaling evidence (not RC0): 4x8 CPUs was 1.34x (24 movies) and 1.68x (96 movies) faster than 1x32 to publication
  (`docs/multi_gpu/scaling/README.md`; source `d7339fd`, 4GPUs). Tomography on real data is unmeasured.
- Throughput scaling at a fixed budget is not a support claim.

## 5. Resume

`--only_do_unfinished` treats a movie as complete when its products exist and each passes a limited check
(`src/motioncorr_runner.cpp:782-824`, `isMovieComplete`):

- each requested MRC (`.mrc`, and `_noDW`, `_EVN`/`_ODD`, `_PS` when requested) has a parseable header, float or float16
  type, `nz = 1` and at least as many bytes as its own header implies (`completeMrc`, `:698-713`);
- the per-movie STAR has positive size fields, the same movie name, a shift for every frame, finite values, and the
  expected frame count when one is given (`:788-818`).

It does **not** compare the MRC geometry with the STAR, and it does **not** compare the settings of the earlier run
with the current ones. Geometry and sampling cross-checks exist only in `--aggregate_only` (`requireAggregateGeometry`,
`:717-777`). This is the #149 limitation, deferred for RC0.

Observed locally (macOS CPU build, 128 x 128 fixture): after a first run, a second run with `--only_do_unfinished`
changed nothing, and a third run adding `--dose_weighting --dose_per_frame 1.5` with the same `--o` also left the
output MRC untouched (same modification time). The consequence: **use a fresh `--o` whenever any processing option,
input, gain or defect file changes.** `run_dataset.py` and `run_multi_gpu.py` refuse an existing output directory for
the same reason.

Unchanged-settings resume, a representative failure, and non-prefix resume on a real dataset are part of the QF
campaign (`docs/release/RELEASE_CHECKLIST.md`) and are **UNRUN** here.

## 6. Failure behaviour that users will see

**This program does not roll back.** Product files are written directly to their destinations
(`submitImageWrite`, `src/motioncorr_runner.cpp:1527-1540`). When a write fails, the output writer cancels the remaining
queued writes and records the failure; it does not remove files that were already written
(`src/output_writer.cpp:102-133`, `src/motioncorr_runner.cpp:1544-1564`). The existing write-fault test resumes a
"truncated leftover" (`tests/test_write_faults.py:21-30`). Therefore a **failed movie** means: no completion STAR for it
and no entry in the joint outputs. It does **not** mean that no file for that movie exists, and **file presence alone is
not success.** After a failure you may find:

- a truncated destination MRC from the write that failed;
- earlier, complete MRC products of the same movie when a later product failed;
- an auxiliary `_PS.mrc` (item 1);
- a per-movie `.log` ending with an `ERROR:` line (`:1544-1564`).

The only case where this page promises that no aligned image was written is a failure before reconstruction
(for example a fatal CUDA error, item 4, which stops before any image is submitted). For everything else, take the
per-movie STAR (the resume completion marker, `:782-824`) together with a successful exit status as the success signal.

**Batches.** When any movie in a run fails, the run exits with an error that names the movies, retains the healthy
movies' per-movie products, and does **not** generate the joint output for the whole batch (`:1083-1089`: "Successful
per-movie outputs were retained; joint output was not generated."). Do not mistake the retained per-movie products of
healthy movies for a published dataset.

1. **`_PS.mrc` can survive a failed movie (inherited behaviour).** With `--grouping_for_ps`, the power spectrum is
   written early, before global alignment (`src/motioncorr_runner.cpp:3309`, output name set at `:2073`). Nothing
   removes it. If patch alignment then fails for the same movie, the movie is marked failed and its aligned products and
   joint outputs are withheld, but `<movie>_PS.mrc` remains. Source: R-SRC review on
   [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6223311256).
2. **A failed Ghostscript render is non-fatal in normal mode and strict in `--aggregate_only`.**
   - `header.pdf` and `batch.pdf`: a failed `gs` run prints "ERROR in executing: gs ..." and, in normal mode, an
     **empty placeholder PDF** is written (`src/CPlot2D.cpp:66-98`). Observed locally without `gs`.
   - `logfile.pdf`: in normal mode the placeholder is explicitly disabled and a failed render neither fails the job nor
     writes a placeholder (`src/motioncorr_runner.cpp:1832-1839`). Locally, without `gs`, a single-process run exited 0
     and wrote `header.pdf` and `batch.pdf` but no `logfile.pdf`.
   - With `--aggregate_only` (and therefore `run_dataset.py`) the same failure is an error (`CPlot2D.cpp:93`).
   - **Fix F1 is merged (#200, `ea86fc90`): a failed render leaves no `logfile.pdf`; strict in `--aggregate_only`.** A failed
     render now removes a partial or earlier regular file (`src/CPlot2D.cpp:30-36, 96`; `src/motioncorr_runner.cpp:1874-1879` for the
     concatenation route). `header.pdf` and `batch.pdf` still get the empty placeholder in normal mode. The absence of `logfile.pdf` therefore means
     "no report was produced", not a successful run; the numerical products are the MRC and STAR files.
3. A pinned `--ingest` that cannot be honoured fails the movie before any host decode (§2).
4. A fatal CUDA error refuses any CPU fallback and fails the movie (`src/motioncorr_runner.cpp:2250-2262`). A
   recoverable device-ingest failure re-reads the movie on the host and continues (`:2310-2315`). The fatal-path CUDA tests inject error
   codes; **genuine device poisoning is not tested** and is post-RC0 work (TST2, [#213](https://github.com/KingAlejandro/MotionCorr-standalone/issues/213)).
5. **Truncated or short raw MRC movies, gain references and defect maps (F3/F3b, D5).**
   - *Today (main `2b3c74b3`):* the read result is discarded, so a truncated raw MRC movie runs to completion and publishes products and a
     completion STAR from partly unread memory (inherited; every mode; float and compact routes publish different unread bytes) (#198 register F3,
     the `Image::read` result is ignored at `src/motioncorr_runner.cpp:2470-2482` and `readData` returns -2 on a short `fread`, `src/image.h:1286`). Validate raw MRC inputs yourself.
   - *Pending, conditional on [PR #205](https://github.com/KingAlejandro/MotionCorr-standalone/pull/205) merging (still in qualification):* a truncated or
     short raw MRC movie, gain reference or defect map fails explicitly instead of publishing products. Until it merges, treat this as not in force.
6. **Compressed MRC (`.bz2`/`.xz`/`.zst`) integrity is not fully checked (F4, documented RC0 limitation, D5).** The decoder's exit status is not
   checked after a complete read (`src/image.h:1948-1953`, `pclose` result ignored, "exit status is not a complete-file integrity check
   here"), so some corruption that is reported only at the end of the stream (for example a missing final byte or a bad index CRC) is
   **accepted**. Short reads are still caught. **You must validate compressed inputs independently before processing**: `xz -t FILE`,
   `zstd -t FILE`, `bzip2 -t FILE` (or `pbzip2 -t FILE`). Scheduled fix: [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214).
7. **Big-endian mode-0 MRC with nx = 128 is not byte-swap detected** (F5; the header swap test is `abs(header->nx) > SWAPTRIG`,
   `src/rwMRC.h:149`); it fails identically on every route. Document-only for RC0 (W-MRC-Q, PR #204).

Auxiliary versus numerical products: the corrected MRC(s) and the per-movie and joint STAR files carry the
results. `logfile.pdf`, `header.pdf`, `batch.pdf`, the shift EPS plots, `.log` and `_PS.mrc` are auxiliary reports.

## 7. Optional dependencies

- **nvCOMP**: `-DUSE_NVCOMP=ON` (default OFF), needs `NVCOMP_ROOT`; not vendored (`CMakeLists.txt:140-153`). Tested with nvCOMP
  5.3.0.16 and CUDA 12.8 (PR #209). See "Optional proprietary dependencies" below.
- **Ghostscript** (`gs`): needed for `logfile.pdf`, `header.pdf` and `batch.pdf`. A single-process run without it still
  writes the MRC, STAR and EPS products, but the PDF reports are absent or empty (§6); `run_dataset.py` fails (§4).
- **pbzip2 / xz / zstd**: only for compressed MRC input (§2). The same tools (`xz -t`, `zstd -t`, `bzip2 -t`/`pbzip2 -t`) are needed to validate compressed inputs first (§6 item 6).
- **Python 3 with NumPy**: required at configure time when `BUILD_TESTING=ON` (`CMakeLists.txt:298-304`); the CMake
  configure fails with "BUILD_TESTING=ON requires Python 3 with 'numpy' installed." (reproduced locally). `README.md` now
  says so beside the build prerequisites. The tools under `tools/` also need NumPy.

### Optional proprietary dependencies (D2, interim policy A)

- **nvCOMP** (tested 5.3.0.16) is **optional and default OFF** (`USE_NVCOMP`), is **not included or vendored** in this repository, and is
  licensed under NVIDIA's SDK agreement, which the user obtains and accepts from NVIDIA.
- **The project distributes no binaries linked against nvCOMP or nvTIFF.**
- Redistribution of such binaries remains subject to licensing review. Anyone who builds and distributes a binary linked against nvCOMP
  (or nvTIFF) must review both licences first.
- **nvTIFF is not used by RC0.**

Basis: maintainer decision D2 on #198 and the decision brief [PR #199](https://github.com/KingAlejandro/MotionCorr-standalone/pull/199) §3.
This page makes no legal claim beyond these statements.

### Decoder trust boundary (D1, option 1: trusted-input precondition; no code change)

On builds configured with `-DUSE_NVCOMP=ON` (default OFF), `--ingest auto` sends **eligible TIFFs** (16-bit, Deflate or Adobe-Deflate, one row per
strip, no predictor, native byte order; full list in §2) to NVIDIA nvCOMP's GPU Deflate decoder. nvCOMP 5.3 documents **undefined behaviour for
corrupt compressed input** (`nvcompBatchedDeflateDecompressAsync`; #134, brief #199). MotionCorr checks the TIFF structure, the zlib wrapper,
sizes and offsets, the decoder status, the decoded length and an Adler-32 checksum before it uses any decoded data, but it **cannot guarantee safe
behaviour on a corrupt Deflate body**. This route therefore **assumes complete, unmodified acquisition files**. **Use `--ingest compact` for
files of unknown integrity or files that are still being written.**

Two further limits: a file that changes **between the tag scan and the strip read is not detected** (follow-up
[#215](https://github.com/KingAlejandro/MotionCorr-standalone/issues/215), post-RC0), and **checked-arithmetic hardening of the pre-decode offset/size
arithmetic is pending (T3)**: it was approved for RC0 (`fix/rc0-nvcomp-checked-arithmetic`) and is not in force until it merges. Update this
paragraph when it does.

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
- **There is no Tier D scientific gate.** No CTF/FSC/B-factor non-inferiority result exists for CPU, CUDA or hybrid output
  (`docs/gate_contract.md` §1; #61, #73 open). RC0 is an evaluation release.
- Tier A (byte-exact CPU regression) and Tier C (known-motion truth) exist and are enforced
  (`docs/gate_contract.md` §1). The CUDA output is not byte-identical to CPU output.
- Standalone versus RELION 5.1: 1/24 byte-identical movies at `--j 1` (#20 open). Same-backend determinism across `--j`
  holds for the CPU build (`docs/gate_contract.md` §7).
- `--max_iter 5` non-convergence: 41 of 50 patches in EMPIAR-10641 and 30 of 50 in EMPIAR-10216 did not converge in the
  #186 pass; those movies spend most of their time in the retry (`docs/workload_corpus/gpu/README.md`). Data dependent.
- Resume (§5). Multi-GPU is process-per-device only (§4).
- **CUDA VRAM floor per geometry.** The resident CUDA path keeps two float-size stacks on the device: the real frames
  and the Fourier half-spectra, each about `frames x nx x ny x 4` bytes. Peak is those two plus 0.7-4.2 GiB of scratch
  (`docs/workload_corpus/gpu/README.md`, VRAM section). EMPIAR-10441 (11520 x 8184 x 50) needs about 35 GiB for the two
  stacks (arithmetic) and peaked at **39.3 GiB** in the #186 GPU pass (NVML, sampled lower bound, 80 GB A100, main
  `116eb04a`), so it does not fit a 24 GiB card and is borderline on 40 GiB (estimate, no small card was run).
  Source shows that if the resident session cannot be initialised the movie takes the **streaming fallback**
  (`src/motioncorr_runner.cpp:2280-2283`, "falling back to streaming pipeline"). What actually happens on an out-of-memory
  allocation inside session initialisation (completion on the streaming path, or a clean failure) is **not qualified**:
  register item QM on #198 is pending. Until QM reports, size the card from the table above rather than relying on the fallback.
  Binning is not recommended as a memory workaround on the strength of this page: source shows that early binning skips
  the resident session (`:2269`) and performs the global FFT on the CPU, but it changes the output sampling and the
  memory behaviour of the later CUDA stages is unqualified.
- **Host RAM with `--grouping_for_ps` on CUDA:** one extra Fourier movie on the host (§3).
- The `ProfilingKit` test has a 30 s subprocess timeout (`tools/profiling/tests/test_import_subset_boundaries.py`) that is load sensitive; it
  failed once under host load about 27 in the Linux CPU qualification and passed on rerun (PR #209). Run CTest on a quiet host, or record it.
- Resident retry (#197), 10641: host RSS 2.07 GiB with the resident retry versus 7.0 GiB before #197; one resident retry allocates 504 MiB of
  VRAM (301 MiB on 10216) (PR #207, single runs).
- Three CPU tests fail or skip on macOS, inherited from main: `SyntheticRegression` (historical Linux reference),
  `MultiGpuScheduling` (tomography endpoint validator) and `NativeMovieStaging` (Linux-only, skipped). Section 3 of
  `docs/release/RELEASE_CHECKLIST.md`.
- `python3 tools/multi_gpu/run_dataset.py` emits a `SyntaxWarning: 'return' in a 'finally' block` on Python 3.14
  (`run_dataset.py:172`). Cosmetic as of this draft.

## 9. Deployment note: huge pages (#188)

On hosts where `/sys/kernel/mm/transparent_hugepage/enabled` is `madvise`, start the process with
`GLIBC_TUNABLES=glibc.malloc.hugetlb=1` (glibc 2.35 or later). On unmodified main the cpu64 24-movie CPU batch went from
508 s to 392 s (4 alternating rounds, one host) with identical output (`docs/host_buffer_reuse.md`;
`docs/issue10_allocator_control/`). THP `always` (SCARF) and `never` were not measured, and no gain is expected on
`always`. The binary prints the host THP mode and any `GLIBC_TUNABLES` on its `Host allocator:` line; record it with any
timing, because timings across hosts with different THP settings are not comparable. The tunable is a deployment setting
and is not set by the program. Qualification: pending RC0 QF.

## 10. Where the evidence lives

`docs/gate_contract.md` (what each gate means), `docs/spa_24_movies_validation.md` (24-movie CPU/RELION comparison),
`docs/cuda_global_alignment_validation.md` (historical CUDA report), `docs/known_motion_validation.md`,
`docs/workload_corpus/` (#186 baselines), `docs/multi_gpu/`, `docs/release/RC0_ACCEPTANCE_REPORT.md` (results of the
frozen-SHA qualification, to be filled).
