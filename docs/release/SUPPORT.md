# MotionCorr RC0 support page (DRAFT)

Status: **draft for RC0, pre-freeze, revision 1** (after the R-REL accuracy review of PR #201). Written against main `1db86902` (see
[#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198)). Source line numbers are at that
revision and will move; re-check them against the frozen SHA. Every **Qualification** cell says
**pending RC0 QF** (the full CPU + native CUDA qualification of the frozen SHA, register item QF in #198).
Nothing on this page is a qualification result. Linux/CUDA command validation is **UNRUN** for this draft.

MotionCorr is an experimental standalone build of RELION 5.1's motion correction (`ad0b230c`, see
`SOURCE_MANIFEST.txt`). It is not an official RELION or MotionCor2 release. An RC0 evaluation release is not a
scientific non-inferiority certificate (Tier D below).

## 1. Supported, experimental and unsupported

| Class | Configuration | Basis | Qualification |
|---|---|---|---|
| Supported (intended) | `--use_own` on CPU, Release build, Linux x86_64 and macOS arm64 | CPU CTest suite; `README.md` build section | pending RC0 QF |
| Supported (intended) | `--use_own --gpu <one id>` on a CUDA build (`-DCUDA=ON`), one process per device | `src/motioncorr_runner.cpp:342-405` | pending RC0 QF |
| Supported (intended) | Several GPUs through `tools/multi_gpu/run_dataset.py` (one process per device) | §4; `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md` | pending RC0 QF |
| Experimental | nvCOMP device Deflate ingest (`-DUSE_NVCOMP=ON`, default OFF) | `CMakeLists.txt:140`; decoder trust boundary, §7 | pending RC0 QF |
| Experimental | `--interpolate_shifts` | help text: "(EXPERIMENTAL)", `src/motioncorr_runner.cpp:212` | pending RC0 QF |
| Not qualified | Every option or input not named in §2 and §3 | no evidence on this page | n/a |
| Unsupported | `--gpu` with a device list under `--use_own` | rejected, `src/motioncorr_runner.cpp:342-370` | refusal verified locally on a CPU build only, §4 |
| Unsupported | `--use_motioncor2` (needs the external MotionCor2 executable) | not part of this program; `src/motioncorr_runner.cpp:222` | n/a |
| Unsupported | One process driving several GPUs (#175), MPI | #175 is parked; `src/motioncorr_runner.cpp:362-367` says the repository has no MPI runner | n/a |
| Unsupported | Resume with changed processing settings in the same `--o` (#149 deferred), §5 | #149 | n/a |
| Not in RC0 (NO-GO) | nvTIFF/LZW device route (#141/#152) | #198 register L1: NO-GO for RC0 integration unless D2 is GO before freeze and a separate complete-product gate passes | n/a |
| Not merged, bounded experiment | nvCOMP Deflate widening to 8-bit samples and any rows-per-strip (#138); device EER renderer (#193 option 2); #179, #181, #183 CPU optimisations | #198 register T1 (merge HOLD pending D1 and its gates), E2, C5-C7 (bounded under the amended rule, [#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6223528151)); none is part of the supported configurations until the coordinator records GO | n/a |

CUDA architecture: `CMakeLists.txt:118-119` defaults `CMAKE_CUDA_ARCHITECTURES` to 80 unless the user or
`CUDAARCHS` sets it. An sm80 binary is not a statement that other devices work.

## 2. Input capability matrix (from current source)

Routes: **CPU** = `--use_own` without CUDA, host reader into float frames. **CUDA float** = host decodes to a float
movie, device does the rest. **CUDA compact** = host decodes into the file's native integer type, the device expands
to float and applies gain. **CUDA nvCOMP** = Deflate strips are decompressed on the device
(`USE_NVCOMP=ON` build only).

`--ingest_witness FILE` appends one line `<movie path> <value>`, `<value>` being `nvcomp`, `compact` or `float`
(`src/motioncorr_runner.cpp:2423-2436`). It writes nothing else. It records the route **selected** for a movie that
reached that point; it is not a record of completion or success:

- a movie skipped by resume is filtered earlier and has no line (`:559-565`);
- a pinned `--ingest` that cannot be honoured fails before the line is appended (`:2313-2317, 2410-2431`), so a
  refusal has no line of its own (use a positive control to prove the intended route);
- compact and float lines are written before the host decode (`:2423-2441`), so a movie that is damaged and then fails
  to decode can still have a line.

On a CPU-only build, and on a CUDA build with no resident CUDA session (for example under default early binning,
`:2264`, or after a session-initialisation failure), the value is `float`.

| Input | Sample type | Compression | CPU | CUDA float | CUDA compact | CUDA nvCOMP | Witness on CUDA, `--ingest auto` | Source | Qualification |
|---|---|---|---|---|---|---|---|---|---|
| TIFF | uint16 | Deflate (8 or 32946) that meets **every** nvCOMP admission test listed below the table | yes | yes (`--ingest float`) | yes (`:2363`) | **yes**, with a live resident session and a successful ingest | `nvcomp` (nvCOMP build) else `compact` | `src/acc/cuda/cuda_movie_session.cu:1420-1463` | pending RC0 QF |
| TIFF | uint16 | Deflate that fails any admission test, or whose ingest declines for budget or arena reasons | yes | yes | yes | declines and logs "nvCOMP ingestion declined (...); using the host reader." (`cuda_movie_session.cu:1479`; budget refusals `:1562, 1679`) | `compact` | same | pending RC0 QF |
| TIFF | uint16 | any other codec LibTIFF decodes (LZW, none, ...) | yes | yes | yes | no (not Deflate) | `compact` | `:2363-2364`; `cuda_movie_session.cu:1448-1449` | pending RC0 QF |
| TIFF | uint8 | any LibTIFF codec | yes | yes | yes | no: requires 16 bits, `cuda_movie_session.cu:1445` | `compact` | `:2363-2364` | pending RC0 QF |
| TIFF | int8, int16 (signed samples) | any | yes | yes | **no**: signed TIFF is read as `SChar`/`SShort`, which the compact TIFF test excludes (`:2363-2364`) | no (also fails the nvCOMP unsigned-sample test) | `float` | `src/rwTIFF.h:119-129` | pending RC0 QF |
| TIFF | float32 | any | yes | yes | no | no | `float` | `src/rwTIFF.h:131` | pending RC0 QF |
| TIFF | 4-bit packed (K2/K3 special case, 8-bit TIFF of K3 super-resolution dimensions) | any | yes | yes | no | no | `float` | `src/rwTIFF.h:100-113` | pending RC0 QF |
| MRC / MRCS | mode 6 (uint16) | none | yes | yes | yes | n/a | `compact` | `src/rwMRC.h:213`; `:2365-2367` | pending RC0 QF |
| MRC / MRCS | mode 1 (int16), mode 0 (**int8, signed**) | none | yes | yes | yes, staged in the signed type (#195) | n/a | `compact` | `src/rwMRC.h:200-205`; `:2365-2367, 2386-2408` | pending RC0 QF |
| MRC / MRCS | mode 2 (float32), mode 12 (float16), mode 101 (4-bit) | none | yes | yes | no | n/a | `float` | `src/rwMRC.h:206, 216-227` | pending RC0 QF |
| MRC / MRCS | modes 3, 4 (complex); any other mode | none | refused at read | refused | refused | n/a | n/a | `src/rwMRC.h:209-228` | pending RC0 QF |
| `.mrc/.mrcs` + `.bz2`/`.xz`/`.zst` | per header | external `pbzip2`, `xz` or `zstd` must be on `PATH`. One sequential frame reader (`:2449`); only `pbzip2` takes a thread count (`-cdkp<N>`, N = the IO-thread setting, `:2126`), `xz -cdk` and `zstd -cdk` take none | yes | yes | **no** (excluded from compact and nvCOMP) | no | `float` | `src/image.h:1814-1851, 1886-1897`; `src/motioncorr_runner.cpp:2284, 2369, 2449` | pending RC0 QF |
| EER | counts, rendered on the host; square 2048 x 2048 or 4096 x 4096 only | EER | yes (float movie) | yes | **yes**, only if `eer_grouping` x (4 if `--eer_upsampling -1`, else 1) <= 65535, rendered into uint16 (#196) | n/a | `compact`, otherwise `float` (logged: "can exceed 65535 counts per pixel; using the float movie") | `:2343-2358`; `src/renderEER.cpp:150-155, 193-195, 232-236` | pending RC0 QF |

Shape and format restrictions the cells above do not repeat:

- **MRC mode 101 (4-bit)** is refused when both nx and ny are odd (`src/rwMRC.h:219-225`).
- **EER upsampling.** The program accepts `-1`, `1`, `2` and `3` (`src/renderEER.cpp:150-155`); the option help says "1 or 2". A 4096 x 4096 movie
  takes -1, 1, 2 and 3; a 2048 x 2048 movie takes only 1 and 2; a movie with 2-bit sub-pixel encoding takes only 1 and 2
  (`:219-236, 573-593`). A TIFF-wrapped EER whose first page is a sum (the TIA variant) is not supported (`:193-195`).
- **EER frame count.** Trailing fractions are dropped: the frame count is `fractions / eer_grouping` with integer
  division (`src/motioncorr_runner.cpp:2120-2122`). This differs from `--group_frames`, which redistributes a remainder into later
  groups (`:2170-2186`).
- **EER corruption.** A fraction whose decoded pixel count does not match is warned about and **skipped**, not failed
  (`src/renderEER.cpp:564-568`). Do not assume every damaged EER file is rejected; `--expected_frames` checks the grouped
  frame count only.
- **EER upsampling memory.** `--eer_upsampling 2` doubles both dimensions (`src/renderEER.cpp:356-375`), so every
  movie buffer is four times larger (upsampling 3: sixteen times). On a CUDA build the resident device buffers are float
  whatever the host staging type, so the uint16 host staging does **not** halve them. The #186 GPU report estimates about
  **75 GiB** for a 144-group 4096 x 4096 EER movie at upsampling 2, "close to the limit of the 80 GB card"; that figure is
  **arithmetic, not run** (`docs/workload_corpus/gpu/README.md`, VRAM section). Treat upsampling 2 on large EER movies as
  unqualified on any card below 80 GB.

Corpus labels, as understood at this revision (the corpus document is not edited by this PR):

- **The RELION tutorial movies are 16-bit Deflate TIFF, one row per strip, with sample values of at most 68** (R-DESIGN
  review on #198; W-TIFF is confirming with `tiffinfo`; not independently re-verified here). This agrees with the
  nvCOMP admission rule (16 bits, one row per strip) and with the #186 witness `nvcomp`. `docs/workload_corpus/corpus.md:17`
  still labels them "u8 Deflate TIFF"; that label is stale and the coordinator is correcting it separately.
- **EMPIAR-10164 is MRC mode 0, which this program reads as signed int8** (`src/rwMRC.h:200-202`), not unsigned.
  `corpus.md:25` labels it "u8 MRC".
- The #186 GPU table (main `116eb04a`) records `float` for every MRC family. #195 (merged `faf5fbdf`) added the raw
  integer MRC compact route; its own evidence records `compact` for modes 0 and 1
  (`docs/issue194_signed_mrc/README.md`). The matrix follows current source, not the older table.

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
| `auto` | nvCOMP if admitted, else compact if admitted, else float | `:2319-2322` |
| `nvcomp` | refused at start-up on a CPU-only build (`:244-245`) and on a CUDA build without `USE_NVCOMP=ON` (`:248-249`). Per movie: error if the device ingest did not run (`:2313-2317`) | as cited |
| `compact` | refused at start-up on a CPU-only build (`:244-245`). Per movie: error if no resident session or the movie is not an eligible type (`:2410-2416`) | as cited |
| `float` | always accepted; disables nvCOMP and compact | `:2283, 2349, 2368` |

Verified locally on a macOS CPU-only Release build (exit status 1 for each refusal): `--ingest compact` and
`--ingest nvcomp` (error at line 245), `--ingest bogus` (line 163); `--ingest float` and `--ingest auto` exit 0, and the
witness for the 128 x 128 MRCS fixture reads `float`. The per-movie refusals need a CUDA build and are **UNRUN**.

## 3. Option matrix

"Source" cites where the option is parsed or where behaviour changes. The CPU column describes the code, not a
qualification. The CUDA column says only what source shows; "not claimed" means this page has no evidence either way.

| Option | CPU | CUDA (`--gpu`) | Source | Qualification |
|---|---|---|---|---|
| Global alignment only (`--patch_x 1 --patch_y 1`, default) | yes | yes, device alignment (resident Fourier frames) | parse `:187-188`; execution `:3319-3325` | pending RC0 QF |
| Local patches (`--patch_x N --patch_y M`) | yes; a value of exactly 2 prints "too small ... Patch based alignment will be skipped" (`:308-314`) | yes, device patch alignment (`:3524-3533`) with resident retry for non-converged patches (#197) | as cited | pending RC0 QF |
| Dose weighting (`--dose_weighting`, `--angpix`, `--voltage`, `--dose_per_frame`, `--preexposure`) | yes; **voltage must be within 2 kV of 100, 200 or 300** or the movie fails | yes, in VRAM when a session is resident; CPU fallback exists | `:4070-4083, 4097` | pending RC0 QF |
| `--save_noDW` | yes (streamed unweighted sum, #178); **needs `--dose_weighting`**: without dose weighting the unweighted sum is the main `.mrc` and no `_noDW.mrc` is written | yes; the CUDA-to-CPU unweighted fallback has **not** been executed natively | `:3355` (`pre_dw_sum_needed`), `:4043-4049`, resume `:789`; #198 item C1 | pending RC0 QF |
| `--even_odd_split` (`_EVN.mrc`, `_ODD.mrc`) | yes | yes | `:3355, 3957-3965` | pending RC0 QF |
| `--bin_factor` (non-integer allowed) | yes; early binning is on by default when binning; **the binned dimensions must both be even** or the movie fails | with early binning the resident session is not created and the global FFT stays on the CPU; later stages still dispatch to CUDA | `:182, 217-219, 2264, 3111-3115, 3141-3147`; late binning `:4949-4951` | pending RC0 QF |
| `--group_frames N` | yes; fewer than 3 groups after grouping skips the movie | not claimed | `:2160-2170` | pending RC0 QF |
| `--eer_grouping`, `--eer_upsampling` | yes; see §2 for accepted values, shapes and the trailing-fraction rule | compact route only within the uint16 limit; **upsampling 2 quadruples the movie storage, about 75 GiB estimated (not run) for 144 groups** (§2) | `:2343-2358` | pending RC0 QF |
| Gain (`--gainref`, `--gain_rot`, `--gain_flip`) | yes; size must match the movie or the movie fails | yes; device gain applied on the compact and nvCOMP routes | `:2203-2216` | pending RC0 QF |
| Defect file (`--defect_file`; `--skip_defect`; `--seed`) | yes; a SerialEM-format `.txt` is rejected. `--skip_defect` skips **both** the automatic hot-pixel detection and the correction with the supplied defect mask (both sit inside `if (!skip_defect)`) | replacement neighbours are read from the typed host staging on the compact routes (`:3019-3034`) and uploaded as sparse replacements; the sparse **device** gather (`gatherFrameSamples`) is used only for nvCOMP input, which has no host frames (`:2944-2958, 3057-3064`) | `:190, 267-272, 2722, 2829`; `cuda_movie_session.cu:1258` | pending RC0 QF |
| `--first_frame_sum`, `--last_frame_sum` | yes; frames outside the range are not used at all | not claimed | `:2147-2155` | pending RC0 QF |
| `--grouping_for_ps`, `--ps_size` (`_PS.mrc`) | yes | **on the resident CUDA path this downloads the whole Fourier movie to the host** (`:3205-3212`), about one complex movie of extra host RAM (roughly the size of one float movie: arithmetic about 17.6 GiB for 11520 x 8184 x 50, not measured); not otherwise claimed | `:3203-3306`; failure behaviour, §6 | pending RC0 QF |
| `--float16` | yes, requires `--grouping_for_ps > 0` | not claimed | `:205, 225-226` | pending RC0 QF |
| `--expected_frames` | yes; a different decoded frame count fails the movie. It is a **fallback**: a per-movie STAR frame count overrides it | same | `:173, 1013-1021, 2136-2141` | pending RC0 QF |
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
  (`src/CPlot2D.cpp:84`), so `run_dataset.py` exited 3.
- Prior evidence (not qualification of RC0): 24 tutorial movies at 1, 2 and 4 GPUs were identical to a single-process
  run, and 4x8 CPUs was 1.34x (24 movies) and 1.68x (96 movies) faster than 1x32 to publication
  (`docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`, `docs/multi_gpu/scaling/README.md`; source `d7339fd`, 4GPUs).
  Tomography on real data is unmeasured (same file).
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
   written early, before global alignment (`src/motioncorr_runner.cpp:3304`, output name set at `:2068`). Nothing
   removes it. If patch alignment then fails for the same movie, the movie is marked failed and its aligned products and
   joint outputs are withheld, but `<movie>_PS.mrc` remains. Source: R-SRC review on
   [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6223311256).
2. **A failed Ghostscript render is non-fatal in normal mode and strict in `--aggregate_only`.**
   - `header.pdf` and `batch.pdf`: a failed `gs` run prints "ERROR in executing: gs ..." and, in normal mode, an
     **empty placeholder PDF** is written (`src/CPlot2D.cpp:66-87`). Observed locally without `gs`.
   - `logfile.pdf`: in normal mode the placeholder is explicitly disabled and a failed render neither fails the job nor
     writes a placeholder (`src/motioncorr_runner.cpp:1832-1839`). Locally, without `gs`, a single-process run exited 0
     and wrote `header.pdf` and `batch.pdf` but no `logfile.pdf`. A render that fails **part-way** can leave a partial
     or stale `logfile.pdf` (R-SRC finding, #198 register F1).
   - With `--aggregate_only` (and therefore `run_dataset.py`) the same failure is an error (`CPlot2D.cpp:84`).
   - **Pending, conditional on fix F1 (branch `fix/rc0-logfile-failed-render`, in progress) merging:** after F1, no
     `logfile.pdf` remains after a failed render. Until F1 is merged and verified, do not use the presence, absence or
     content of `logfile.pdf` as a success signal.
3. A pinned `--ingest` that cannot be honoured fails the movie before any host decode (§2).
4. A fatal CUDA error refuses any CPU fallback and fails the movie (`src/motioncorr_runner.cpp:2245-2257`). A
   recoverable device-ingest failure re-reads the movie on the host and continues (`:2305-2310`).

Auxiliary versus numerical products: the corrected MRC(s) and the per-movie and joint STAR files carry the
results. `logfile.pdf`, `header.pdf`, `batch.pdf`, the shift EPS plots, `.log` and `_PS.mrc` are auxiliary reports.

## 7. Optional dependencies

- **nvCOMP**: `-DUSE_NVCOMP=ON` (default OFF), needs `NVCOMP_ROOT`; not vendored (`CMakeLists.txt:140-153`). The #186 and
  #194 evidence used nvCOMP 5.3 with CUDA 12.8 (`docs/workload_corpus/gpu/README.md`). Licence compatibility with
  GPL-2.0-or-later is an open maintainer decision (D2 on #198). Pending.
- **Ghostscript** (`gs`): needed for `logfile.pdf`, `header.pdf` and `batch.pdf`. A single-process run without it still
  writes the MRC, STAR and EPS products, but the PDF reports are absent or empty (§6); `run_dataset.py` fails (§4).
- **pbzip2 / xz / zstd**: only for compressed MRC input (§2).
- **Python 3 with NumPy**: required at configure time when `BUILD_TESTING=ON` (`CMakeLists.txt:298-304`); the CMake
  configure fails with "BUILD_TESTING=ON requires Python 3 with 'numpy' installed." (reproduced locally). `README.md` now
  says so beside the build prerequisites. The tools under `tools/` also need NumPy.

### Decoder trust boundary (placeholder)

**Pending decisions D1, D2 and T3 on #198 (decision brief: [PR #199](https://github.com/KingAlejandro/MotionCorr-standalone/pull/199), being revised); this section is a placeholder and states no policy.** T3 is the open question whether the unchecked offset/size arithmetic in the nvCOMP pre-decode path is hardened for RC0 or after it. What source and #134
support today: the nvCOMP Deflate route checks TIFF eligibility, the zlib wrapper, chunk statuses, decoded sizes and
Adler-32, but NVIDIA documents that corrupt compressed input to `nvcompBatchedDeflateDecompressAsync` can produce
undefined behaviour and that error reporting is not guaranteed (#134). Until D1 is decided, nvCOMP ingest must not be
described as safe against malformed or growing input files. Use immutable, trusted movie files with `--ingest auto`
on an nvCOMP build, or `--ingest float`/`compact` to avoid the device decoder.

## 8. Known limitations

- **The `0.001` relative-RMSE diagnostic fails for CUDA versus CPU.** On the 24 tutorial movies CUDA versus fixed CPU
  `--j 1` gives relative RMSE 0.002899-0.010082 against 0.001 (0/24 pass the relaxed profile; every other relaxed check
  passes). The explicit `--gate backend` profile records this as a non-blocking diagnostic. This is a strict CPU-agreement
  measurement, not a statement about scientific validity. `docs/gate_contract.md` §3, §7;
  `docs/cuda_global_alignment_validation.md`; `docs/cuda_24_movies_gate2_rerun.json`. These are historical results and do not
  describe the RC0 composition.
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
  (`src/motioncorr_runner.cpp:2275-2278`, "falling back to streaming pipeline"). What actually happens on an out-of-memory
  allocation inside session initialisation (completion on the streaming path, or a clean failure) is **not qualified**:
  register item QM on #198 is pending. Until QM reports, size the card from the table above rather than relying on the fallback.
  Binning is not recommended as a memory workaround on the strength of this page: source shows that early binning skips
  the resident session (`:2264`) and performs the global FFT on the CPU, but it changes the output sampling and the
  memory behaviour of the later CUDA stages is unqualified.
- **Host RAM with `--grouping_for_ps` on CUDA:** one extra Fourier movie on the host (§3).
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
