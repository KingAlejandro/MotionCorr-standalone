# MotionCorr RC0 support page (DRAFT)

Status: **draft for RC0, pre-freeze.** Written against main `1db86902` (see
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
| Not in RC0 | nvTIFF/LZW device route (#141/#152), device EER renderer (#193 option 2), nvCOMP widening (#138) | #198 register: L1, E2, T1 | n/a |

CUDA architecture: `CMakeLists.txt:118-119` defaults `CMAKE_CUDA_ARCHITECTURES` to 80 unless the user or
`CUDAARCHS` sets it. An sm80 binary is not a statement that other devices work.

## 2. Input capability matrix (from current source)

Routes: **CPU** = `--use_own` without CUDA, host reader into float frames. **CUDA float** = host decodes to a float
movie, device does the rest. **CUDA compact** = host decodes into the file's native integer type, the device expands
to float and applies gain. **CUDA nvCOMP** = Deflate strips are decompressed on the device
(`USE_NVCOMP=ON` build only).

`--ingest_witness FILE` appends one line `<movie path> <value>` per movie, `<value>` being `nvcomp`, `compact` or
`float` (`src/motioncorr_runner.cpp:2423-2436`). It writes nothing else. On a CPU-only build, and on a CUDA build
with no resident CUDA session (for example under default early binning, `:2264`, or after a session-initialisation
failure), the value is `float`.

| Input | Sample type | Compression | CPU | CUDA float | CUDA compact | CUDA nvCOMP | Witness on CUDA, `--ingest auto` | Source | Qualification |
|---|---|---|---|---|---|---|---|---|---|
| TIFF | uint16 | Deflate (8 or 32946), no predictor, one row per strip, one sample, contiguous, native byte order | yes | yes (`--ingest float`) | yes (`:2363`) | **yes**, if every condition in the first column holds | `nvcomp` (nvCOMP build) else `compact` | `src/acc/cuda/cuda_movie_session.cu:1420-1457` | pending RC0 QF |
| TIFF | uint16 | Deflate that fails any admission test (predictor 2, rows-per-strip > 1, non-native byte order, signed samples) | yes | yes | yes | declines, logs "nvCOMP ingestion declined (...); using the host reader." (`cuda_movie_session.cu:1479`) | `compact` | same | pending RC0 QF |
| TIFF | uint16 | any other codec LibTIFF decodes (LZW, none, ...) | yes | yes | yes | no (not Deflate) | `compact` | `:2363-2364`; `cuda_movie_session.cu:1448-1449` | pending RC0 QF |
| TIFF | uint8 | any LibTIFF codec | yes | yes | yes | no: requires 16 bits, `cuda_movie_session.cu:1445` | `compact` | `:2363-2364` | pending RC0 QF |
| TIFF | int8, int16 | any | yes | yes | **no** (the compact test admits only `UShort`/`UChar`, `:2363-2364`) | no | `float` | `src/rwTIFF.h:115-131` | pending RC0 QF |
| TIFF | float32 | any | yes | yes | no | no | `float` | `src/rwTIFF.h:131` | pending RC0 QF |
| TIFF | 4-bit packed (K2/K3 special case, 8-bit TIFF of K3 super-resolution dimensions) | any | yes | yes | no | no | `float` | `src/rwTIFF.h:100-113` | pending RC0 QF |
| MRC / MRCS | mode 6 (uint16) | none | yes | yes | yes | n/a | `compact` | `src/rwMRC.h:213`; `:2365-2367` | pending RC0 QF |
| MRC / MRCS | mode 1 (int16), mode 0 (**int8, signed**) | none | yes | yes | yes, staged in the signed type (#195) | n/a | `compact` | `src/rwMRC.h:200-205`; `:2365-2367, 2386-2408` | pending RC0 QF |
| MRC / MRCS | mode 2 (float32), mode 12 (float16), mode 101 (4-bit) | none | yes | yes | no | n/a | `float` | `src/rwMRC.h:206, 216-227` | pending RC0 QF |
| MRC / MRCS | modes 3, 4 (complex); any other mode | none | refused at read | refused | refused | n/a | n/a | `src/rwMRC.h:209-228` | pending RC0 QF |
| `.mrc/.mrcs` + `.bz2`/`.xz`/`.zst` | per header | external `pbzip2`, `xz` or `zstd` must be on `PATH`; one decode thread | yes | yes | **no** (excluded from compact and nvCOMP) | no | `float` | `src/image.h:1814-1851`; `src/motioncorr_runner.cpp:2284, 2369, 2449` | pending RC0 QF |
| EER | counts, rendered on the host | EER | yes (float movie) | yes | **yes**, only if `eer_grouping` x (4 if `--eer_upsampling -1`, else 1) <= 65535, rendered into uint16 (#196) | n/a | `compact`, otherwise `float` (logged: "can exceed 65535 counts per pixel; using the float movie") | `:2343-2358` | pending RC0 QF |

Mismatches to resolve before the matrix is final:

- `docs/workload_corpus/corpus.md:17` labels the tutorial "u8 Deflate TIFF". nvCOMP admission requires 16 bits
  (`cuda_movie_session.cu:1445`), and the #186 GPU pass witnessed `nvcomp` for the tutorial
  (`docs/workload_corpus/gpu/README.md`). One of these is wrong about the bit depth. Open with W-TIFF; not resolved here.
- `corpus.md:25` labels EMPIAR-10164 "u8 MRC". It is mode 0, which this program reads as **signed** int8
  (`src/rwMRC.h:200-202`).
- The #186 GPU table (main `116eb04a`) records `float` for every MRC family. #195 (merged `faf5fbdf`) added the raw
  integer MRC compact route; its own evidence records `compact` for modes 0 and 1
  (`docs/issue194_signed_mrc/README.md`). The matrix above follows current source, not the older table.

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
| Global alignment only (`--patch_x 1 --patch_y 1`, default) | yes | yes, device alignment | `:187-188` | pending RC0 QF |
| Local patches (`--patch_x N --patch_y M`) | yes; a value of exactly 2 prints "too small ... Patch based alignment will be skipped" | yes, device patch alignment with resident retry for non-converged patches (#197) | `:303-312` | pending RC0 QF |
| Dose weighting (`--dose_weighting`, `--angpix`, `--voltage`, `--dose_per_frame`, `--preexposure`) | yes | yes, in VRAM when a session is resident; CPU fallback exists | `:4085-4125` | pending RC0 QF |
| `--save_noDW` | yes (streamed unweighted sum, #178) | yes; the CUDA-to-CPU unweighted fallback has **not** been executed natively | `:3355` (`pre_dw_sum_needed`); #198 item C1 | pending RC0 QF |
| `--even_odd_split` (`_EVN.mrc`, `_ODD.mrc`) | yes | yes | `:3355, 3957-3965` | pending RC0 QF |
| `--bin_factor` (non-integer allowed) | yes; early binning is on by default when binning | with early binning the resident session is not created and the global FFT stays on the CPU; later stages still dispatch to CUDA | `:182, 217-219, 2264, 3141-3147` | pending RC0 QF |
| `--group_frames N` | yes; fewer than 3 groups after grouping skips the movie | not claimed | `:2160-2170` | pending RC0 QF |
| `--eer_grouping`, `--eer_upsampling` | yes | compact route only within the uint16 limit (§2) | `:2343-2358` | pending RC0 QF |
| Gain (`--gainref`, `--gain_rot`, `--gain_flip`) | yes; size must match the movie or the movie fails | yes; device gain applied on the compact and nvCOMP routes | `:2203-2216` | pending RC0 QF |
| Defect file (`--defect_file`; `--skip_defect`; `--seed`) | yes; a SerialEM-format `.txt` is rejected | hot-pixel and defect replacement are handled with device gather (`gatherFrameSamples`) | `:190, 267-272`; `cuda_movie_session.cu:1258` | pending RC0 QF |
| `--first_frame_sum`, `--last_frame_sum` | yes; frames outside the range are not used at all | not claimed | `:2147-2155` | pending RC0 QF |
| `--grouping_for_ps`, `--ps_size` (`_PS.mrc`) | yes | not claimed | `:3244-3306`; failure behaviour, §6 | pending RC0 QF |
| `--float16` | yes, requires `--grouping_for_ps > 0` | not claimed | `:205, 225-226` | pending RC0 QF |
| `--expected_frames` | yes; a different decoded frame count fails the movie | same | `:2136-2141` | pending RC0 QF |
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

`--only_do_unfinished` treats a movie as complete when its products exist and parse: a float or float16 MRC of
consistent size, the optional `_noDW`, `_EVN`/`_ODD` and `_PS` MRCs, and a per-movie STAR whose frame count, size,
movie name and shifts are consistent (`src/motioncorr_runner.cpp:782-824`, `isMovieComplete`). It does **not** compare
the settings of the earlier run with the current ones. This is the #149 limitation, deferred for RC0.

Observed locally (macOS CPU build, 128 x 128 fixture): after a first run, a second run with `--only_do_unfinished`
changed nothing, and a third run adding `--dose_weighting --dose_per_frame 1.5` with the same `--o` also left the
output MRC untouched (same modification time). The consequence: **use a fresh `--o` whenever any processing option,
input, gain or defect file changes.** `run_dataset.py` and `run_multi_gpu.py` refuse an existing output directory for
the same reason.

Unchanged-settings resume, a representative failure, and non-prefix resume on a real dataset are part of the QF
campaign (`docs/release/RELEASE_CHECKLIST.md`) and are **UNRUN** here.

## 6. Failure behaviour that users will see

A **failed movie** means: no completion STAR for that movie, no aligned MRC and no entry in the joint outputs. It does
not mean that no file for that movie exists.

1. **`_PS.mrc` can survive a failed movie (inherited behaviour).** With `--grouping_for_ps`, the power spectrum is
   written early, before global alignment (`src/motioncorr_runner.cpp:3304`, with the output name set at `:2068`).
   Nothing removes it. If patch alignment then fails for the same movie, the movie is marked failed and its aligned
   products and joint outputs are withheld, but `<movie>_PS.mrc` remains on disk. Treat the per-movie STAR, not the
   presence of `_PS.mrc`, as the completion marker. Source: R-SRC review on
   [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6223311256).
2. **A failed Ghostscript render of `logfile.pdf` is non-fatal in normal mode and strict in `--aggregate_only`.**
   In normal mode a failed `gs` run prints "ERROR in executing: gs ..." and the run continues
   (`src/CPlot2D.cpp:66-87`); the placeholder behaviour there can leave an empty PDF. Locally, without `gs`, a
   single-process run exited 0 and wrote `header.pdf` and `batch.pdf` but no `logfile.pdf`, and printed the gs
   error. With `--aggregate_only` (and therefore `run_dataset.py`) the same failure is an error (`CPlot2D.cpp:84`).
   **Pending, conditional on fix F1 (branch `fix/rc0-logfile-failed-render`, in progress) merging:** after F1, no
   `logfile.pdf` remains after a failed render. Until F1 is merged and verified, do not rely on the absence or the
   content of `logfile.pdf` as a success signal; the numerical products are the MRC and STAR files.
3. A pinned `--ingest` that cannot be honoured fails the movie (§2).
4. A fatal CUDA error refuses any CPU fallback and fails the movie (`src/motioncorr_runner.cpp:2245-2257`). A
   recoverable device-ingest failure re-reads the movie on the host and continues (`:2305-2310`).

Auxiliary versus numerical products: the corrected MRC(s) and the per-movie and joint STAR files carry the
results. `logfile.pdf`, the shift EPS plots, `.log` and `_PS.mrc` are auxiliary reports.

## 7. Optional dependencies

- **nvCOMP**: `-DUSE_NVCOMP=ON` (default OFF), needs `NVCOMP_ROOT`; not vendored (`CMakeLists.txt:140-153`). The #186 and
  #194 evidence used nvCOMP 5.3 with CUDA 12.8 (`docs/workload_corpus/gpu/README.md`). Licence compatibility with
  GPL-2.0-or-later is an open maintainer decision (D2 on #198). Pending.
- **Ghostscript** (`gs`): needed for `logfile.pdf` and `header.pdf`/`batch.pdf`. A single-process run without it still writes
  the MRC, STAR and EPS products; `run_dataset.py` fails (§4). `README.md` build section.
- **pbzip2 / xz / zstd**: only for compressed MRC input (§2).
- **Python 3 with NumPy**: required at configure time when `BUILD_TESTING=ON` (`CMakeLists.txt:298-304`); the CMake
  configure fails with "BUILD_TESTING=ON requires Python 3 with 'numpy' installed." (reproduced locally; the README
  build command does not mention it). The tools under `tools/` also need NumPy.

### Decoder trust boundary (placeholder)

**Pending decisions D1 and D2 on #198; this section is a placeholder and states no policy.** What source and #134
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
- CUDA VRAM: peak is about two resident float32 movies plus 0.7-4.2 GiB. Frames x size that exceed the card fail; EMPIAR-10441
  (11520 x 8184 x 50) peaked at 39.3 GiB (`docs/workload_corpus/gpu/README.md`, VRAM section). See also the
  RC0 acceptance report skeleton.
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
