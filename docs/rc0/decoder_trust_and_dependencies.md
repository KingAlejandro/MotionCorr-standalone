# RC0 decision brief: decoder trust boundary (D1) and proprietary optional dependencies (D2)

Coordination: #198 (D1, D2, T1, T2, L1). Inputs: #134, #141, #193, PR #138, PR #151, PR #152,
`experiment/nvtiff-timing-20261016`. Source revision read: `main` =
`1db869025507ac801845b4001b84e6bc0e77a645`. This is a documentation brief. It changes no
source and decides nothing; each option below is for the maintainer to choose.

**Section 3 is not legal advice. Licence compatibility is a maintainer decision.**

## 1. Summary

| | Current state | Options | Brief's recommendation |
|---|---|---|---|
| D1 | `--ingest auto` on a `USE_NVCOMP=ON` build sends eligible u16 one-row-per-strip Deflate TIFF strips to nvCOMP. NVIDIA documents undefined behaviour for corrupt input. Main's checks are output-integrity checks; nothing validates the Deflate body before the decoder runs. | (1) documented trusted/immutable-input precondition for auto; (2) GPU decoder only on explicit opt-in; (3) full CPU inflate before GPU decode | Option 1 for the existing u16 route, option 2 for any newly admitted population (#138 widening, nvTIFF). Section 4.5. |
| D2 | nvCOMP is `option(USE_NVCOMP OFF)`, found with `find_library`, never vendored; CI builds without it; the project distributes no binaries. nvTIFF exists only on unmerged branch #152. | A: keep optional/off/not vendored, add a notice, distribute no linked binaries; B: also distribute linked binaries; C: exclude proprietary optional dependencies; D: ask NVIDIA / counsel first | A for nvCOMP. nvTIFF stays out of RC0 whatever is chosen. Section 3.5. |
| nvTIFF | Standalone decode exact; SCARF timing GO (0.89 s/movie); VM unresolved; malformed-LZW safety unproven; no application route | — | Not in RC0 unless D1 and D2 permit it **and** a complete-product integration gate passes before freeze. Section 5. |

## 2. Vendor contracts as installed

All files were read in place, read-only. Hashes are `sha256sum` on the host named.

### 2.1 nvCOMP 5.3.0.16 (4GPUs, `~/nvcomp53/`)

| File | sha256 |
|---|---|
| `nvcomp.tar.xz` (archive as downloaded) | `1def6bb0fa51d8ea3fe0c43ae1c58df2f63808ced7444267e14245583ec23f6f` |
| `nvidia_nvcomp_cu12-5.3.0.16-…manylinux_2_28_x86_64.whl` | `c2cb2bd40b2a97381a46b3645f8e1b401325b6828c1f227b7685c9ee86412749` |
| `nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/LICENSE` (identical in the wheel's `dist-info/licenses/`) | `cbe5c7e94b5c7247fb92cf8920bdbd82631e234b2bf08340526f492080175b82` |
| `…/NOTICE` (third-party notices: zstd, zlib-style Mark Adler code, {fmt}, pybind11) | `f39d9c3ad5b193f28169e028d1db070980ae1303a39d70054a16a08f4934cb88` |
| `…/include/nvcomp/deflate.h` | `c21aaa7c2ea725bdf19490819a08a276a2c0b02e2ed2ac6a93de70b882101464` |
| `…/include/nvcomp/version.h` | `f017fbe17b7d72338064cb7d546fca361fb9f73e7a51cd5abe2a99a73ba036a8` |
| `…/lib/libnvcomp.so.5.3.0.16` | `1ef190104637b1ecd4f4b9a2e13bb62c131e1828512bf6d5c907e1dd19b23ca5` |

`version.h` defines `NVCOMP_VER_MAJOR 5`, `MINOR 3`, `PATCH 0`, `BUILD 16`. This matches the
5 October native acceptance (CUDA 12.8.61 / nvCOMP 5.3.0.16, #134). The CUDA 12.8 toolkit on
4GPUs (`/usr/local/cuda-12.8/lib64`) contains no nvCOMP or nvTIFF library. 11 of the 12
`include/nvcomp/*.h` headers carry `SPDX-License-Identifier: LicenseRef-NvidiaProprietary`;
`version.h` carries a BSD-3-style notice.

`deflate.h`, documentation of `nvcompBatchedDeflateDecompressAsync`, lines 414–418:

> ` * @warning Violating any of the conditions listed in the parameter descriptions`
> ` * below may result in undefined behaviour.`
> ` *`
> ` * @warning Providing a corrupt buffer for decompression will result in undefined`
> ` * behavior irrespective of the decompression backend used.`

Lines 432–435, on output capacity:

> ` * The sizes should reside in device-accessible memory. If a`
> ` * size is not large enough to hold all decompressed data, the decompressor`
> ` * will set the status in \p device_statuses corresponding to the`
> ` * overflow chunk to `nvcompErrorCannotDecompress`.`

Lines 457–461, on `device_statuses`:

> ` * device-accessible memory. This argument needs to be preallocated. For each`
> ` * chunk, if the decompression is successful, the status will be set to`
> ` * `nvcompSuccess`. Passing corrupt, invalid, or insufficient data leads to`
> ` * undefined behavior or out-of-bound errors. Error reporting cannot be guaranteed`
> ` * in this scenario as only a limited validation is performed to maintain performance.`

So the installed 5.3 contract is the same as the published one cited in #134: a status or a
correct length after decode is not evidence that a corrupt stream was handled safely.

### 2.2 nvTIFF 0.8.0.82 (4GPUs and SCARF, byte-identical)

Paths recorded in PR #152 `native_20261006.json` and `timing_20261016/RESULT.md`:

- 4GPUs: `~/motioncorr-nvtiff-native-v2-20261006/private-sdk/` (wheel and `unpacked/`)
- SCARF: `/work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff/` (`sdk-download/`, `sdk-0.8.0.82/`)

| File | sha256 (same on both hosts) |
|---|---|
| `nvidia_nvtiff_cu12-0.8.0.82-py3-none-manylinux2014_x86_64.whl` | `2d4a2ea3b749d78fe446df496235469a4cb71eb64deff907e74f02eaa4a70cdf` |
| `nvidia_nvtiff_cu12-0.8.0.82.dist-info/licenses/LICENSE.txt` | `33724527ccac9519fc9fe8fb339e660600d99783572fd64f103ed453a91abc7a` |
| `nvidia/nvtiff/include/nvtiff.h` | `e0e3116544d1c7bd40dacd689bf2d5b7f90389fc6a54ec5e13ebc569988460d1` |
| `nvidia/nvtiff/lib/libnvtiff.so.0` | `d46cfdef19db2530a5cfe06cc093edba7592d51656f1cbf833d51ce60b8a7830` |
| `nvidia/nvtiff/include/nvtiff_version.h` (4GPUs) | `95042afb2f67c8312e0dbd5e39a8174fb8786898f5c761fc0a8da7e2cc895681` |
| `dist-info/METADATA` (4GPUs) | `2f1c288bc9b9d8cab03438a294aadc2b81f24688cda5af98e6bdca43c0749e5f` |

`nvtiff_version.h`: `NVTIFF_VER_MAJOR 0`, `MINOR 8`, `PATCH 0`, `BUILD 82`. `METADATA` states
`License: NVIDIA Proprietary Software` and `Classifier: Development Status :: 4 - Beta`.
The two headers carry an MIT-style permission notice; the shared library is governed by
`LICENSE.txt`. The wheel ships no other documentation.

**Malformed-input behaviour.** The header documents TIFF-structure errors only. `nvtiff.h`
line 66:

> `    NVTIFF_STATUS_BAD_TIFF = 3, /**< Cannot parse the TIFF stream. Likely due to a corruption that cannot be handled. */`

Lines 634–636:

> ` * Opening returns an error for an I/O failure (missing or unreadable file) or a malformed TIFF`
> ` * header (bad magic or version); an IFD whose structure or contents are invalid reports`
> ` * @c ::NVTIFF_STATUS_BAD_TIFF when it is first accessed. On any failure @c *tiff_stream is set to`

Lines 925–928 (`nvtiffDecode`):

> ` * @note A decoder may have only one decode in flight at a time. Every call to @ref nvtiffDecode`
> ` * must be followed by stream completion (for example @c cudaStreamSynchronize), regardless of the`
> ` * returned status, before the same decoder is reused or destroyed. The decoder reuses internal`
> ` * scratch buffers and may have submitted work before reporting an error. To decode concurrently,`

Line 70: `NVTIFF_STATUS_EXECUTION_FAILED   = 6,  /**< Error during the execution of the device tasks. */`

The header says nothing about corrupt **compressed strip data** (LZW or otherwise): it neither
promises detection nor warns of undefined behaviour. The published landing page
(`docs.nvidia.com/cuda/nvtiff/index.html`, fetched 2026-10-16) also has no such text. Absence
of a warning is not a guarantee; for planning, nvTIFF must be treated like nvCOMP. Unlike
nvCOMP, nvTIFF also parses the TIFF structure itself, so its trust boundary includes IFD
parsing that MotionCorr's own LibTIFF admission does today.

### 2.3 Licence clauses (quoted exactly)

nvCOMP `LICENSE` ("LICENSE AGREEMENT FOR NVIDIA SOFTWARE DEVELOPMENT KITS", v. April 26, 2022)
and nvTIFF `LICENSE.txt` (same agreement, v. March 31, 2022, plus an nvTIFF supplement) have the
same structure. Line numbers are in the respective file.

| Topic | nvCOMP `LICENSE` | nvTIFF `LICENSE.txt` |
|---|---|---|
| Grant: use | l.21 "(i) Install and use the SDK," | l.38 "1. Install and use the SDK," |
| Grant: redistribution | l.25 "(ii) Distribute the binary files, files identified as samples, and headers as incorporated into a software application that meets the distribution requirements indicated in this Agreement." | l.40 "3. Distribute those portions of the SDK that are identified in this Agreement as distributable, as incorporated in object code format into a software application that meets the distribution requirements indicated in this Agreement." |
| What is distributable | the grant above | l.150 "2. Distribution. The following portions of the SDK are distributable under the Agreement: the runtime files .so and .h, nvTIFF_0.dll, nvTIFF.lib and libnvTIFF_static.a." |
| Distribution requirements | l.31 "(i) Your application must have material additional functionality, beyond the included portions of the SDK." l.33 "(ii) The distributable portions of the SDK shall only be accessed by your application." l.39 "(v) The terms under which you distribute your application must be consistent with the terms of this Agreement, including (without limitation) terms relating to the license grant and license restrictions and protection of NVIDIA's intellectual property rights. …" | l.44, l.45, l.48: same text (items 1, 2, 5) |
| Attribution | l.35 "(iii)  The following notice shall be included in modifications and derivative works of sample source code distributed: "This software contains source code provided by NVIDIA Corporation."" | l.46: same |
| Open-source licences | l.87 "2.6 You may not use the SDK in any manner that would cause it to become subject to an open source software license. As examples, licenses that require as a condition of use, modification, and/or distribution that the SDK be (i) disclosed or distributed in source code form; (ii) licensed for the purpose of making derivative works; or (iii) redistributable at no charge." | l.81 "2.5 …" same text |
| Linking | no clause names static or dynamic linking; nvTIFF lists `libnvTIFF_static.a` as distributable (l.150) | same |
| Pre-release | l.55 "You may use a pre-release SDK at your own risk, understanding that pre-release SDKs are not intended for use in production or business-critical systems." | l.60: same; l.58 applies it to "The SDK versions identified as alpha, beta, preview or otherwise as pre-release" |
| GPUs | l.77 "2.1 The SDK is licensed for you to develop applications only for use in systems with NVIDIA GPUs." | l.149 "1. License Scope. …" same |
| Academic users | l.47 "If you are an academic institution you may allow users enrolled or employed by the academic institution to access and use the SDK from your secure network." | l.54: same |
| Questions | l.143 "… please contact NVIDIA at nvidia-compute-license-questions@nvidia.com." | l.151: same |

## 3. D2 — proprietary optional dependencies and GPL-2.0-or-later

**Not legal advice; maintainer decision.** This section identifies the clauses that bear on the
decision and where the risk sits. It does not establish compatibility.

### 3.1 Facts on main

- `LICENSE` and `COPYING` are the same GPL-2.0 text (sha256
  `231f7edcc7352d7734a96eef0b8030f77982678c516876fcb81e25b32d68564c`). README states RELION's
  GPL-2.0-or-later terms apply. Most of the code is RELION-derived; its copyright holders are
  the RELION authors, not this project.
- `CMakeLists.txt:140–153`: `option(USE_NVCOMP … OFF)`; `find_path`/`find_library` against
  `NVCOMP_ROOT`; link only when ON; `FATAL_ERROR` if requested and absent. Calls are behind
  `_NVCOMP_ENABLED`, checked by the `NvcompGuards` test.
- No NVIDIA header, library or sample code is in the tree. No file under `src/`, `tests/`,
  `tools/` carries an NVIDIA copyright notice.
- CI (`.github/workflows/ci.yml`) builds CPU and CUDA without nvCOMP and uploads no artefacts.
  There is no release binary.
- README and `SOURCE_MANIFEST.txt` do not mention nvCOMP. `SOURCE_MANIFEST.txt` records
  RELION-imported files only.
- Every CUDA build already links proprietary NVIDIA libraries (`CUDA::cudart`, `CUDA::cufft`,
  `CMakeLists.txt:138`), as RELION's own CUDA build does. nvCOMP and nvTIFF differ: they are
  optional, separately downloaded SDKs, not part of the installed CUDA toolkit.

### 3.2 The relevant GPL text

`COPYING` lines 72–76:

> Activities other than copying, distribution and modification are not
> covered by this License; they are outside its scope.  The act of
> running the Program is not restricted, and the output from the Program
> is covered only if its contents constitute a work based on the
> Program (independent of having been made by running the Program).

`COPYING` lines 155–164 (section 3, the system-library exception):

> The source code for a work means the preferred form of the work for
> making modifications to it.  For an executable work, complete source
> code means all the source code for all modules it contains, plus any
> associated interface definition files, plus the scripts used to
> control compilation and installation of the executable.  However, as a
> special exception, the source code distributed need not include
> anything that is normally distributed (in either source or binary
> form) with the major components (compiler, kernel, and so on) of the
> operating system on which the executable runs, unless that component
> itself accompanies the executable.

### 3.3 Analysis by distribution scenario

| Scenario | GPL side | NVIDIA side | Risk reading |
|---|---|---|---|
| S1. Project distributes **source only**; nvCOMP/nvTIFF are optional and found at configure time | The distributed source contains no NVIDIA material. GPL obligations attach to distribution of the source, which the project can meet. | No SDK material is distributed, so the distribution grant is not exercised. | Low. This is the current nvCOMP position. |
| S2. A user or site **builds with `USE_NVCOMP=ON` for its own use** (including an academic institution's own users, NVIDIA l.47) | Running and private modification are outside GPL obligations (l.72–76); nothing is distributed. | The user accepts NVIDIA's agreement when obtaining the SDK. | Low for the project. The user needs the SDK licence. |
| S3. Someone **distributes a binary linked against** nvCOMP/nvTIFF, without the library (recipient installs it) | Section 3 requires complete source for "all modules it contains". The system-library exception covers components "normally distributed … with the major components … of the operating system". A separately downloaded SDK, absent from the CUDA toolkit, is unlikely to fit that wording. Whether a dynamically linked library is a "module" of the work is the long-disputed question; the GPL text does not settle it. | §2.6 (nvCOMP) / §2.5 (nvTIFF) forbid use "in any manner that would cause it to become subject to an open source software license". | Material. Needs counsel. |
| S4. Someone **distributes a binary bundled with** `libnvcomp`/`libnvtiff` (container, conda, module tree) | The exception ends where the component "itself accompanies the executable", so it cannot apply. | Distribution requirements l.31–41 apply, including (v) "consistent with the terms of this Agreement"; distributing under GPL terms that would require source or free redistribution conflicts with §2.6/§2.5. nvCOMP's `NOTICE` third-party texts would also have to ship. | High. Do not do this without counsel and, likely, NVIDIA's written position. |

Further limits:

- **No project-level linking exception is available.** An additional permission to link a
  proprietary library would need every copyright holder of the GPL code in the combined work.
  The RELION-derived code is not this project's to relicense.
- **"Optional and default-off" does not settle S3/S4.** It keeps the project in S1/S2 by
  default; it does not change what a third party who builds and distributes a linked binary
  must consider. #141 and PR #152 already say this.
- **nvTIFF adds a pre-release question.** The wheel declares `Development Status :: 4 - Beta`
  and version 0.8. The agreement says pre-release SDKs "are not intended for use in
  production or business-critical systems" (nvTIFF l.60). Whether the classifier "identifies"
  the release as pre-release is for NVIDIA or counsel. This bears on promotion even under S1/S2.
- **Headers.** nvCOMP headers are `LicenseRef-NvidiaProprietary`; nvTIFF headers are MIT.
  Neither is vendored, so this matters only if headers were ever copied into the tree. Do not.

### 3.4 Notices each option would need

| Where | Needed now (S1/S2) | Needed if binaries were distributed (S3/S4) |
|---|---|---|
| README, "Optional proprietary dependencies" | Yes, recommended: name and tested version (nvCOMP 5.3.0.16); licence is NVIDIA's SDK agreement; not included; user obtains it from NVIDIA and accepts its terms; `USE_NVCOMP` is OFF by default; the project distributes no binary linked against it, and anyone who does should review both licences first | Same, plus the redistribution terms actually relied on |
| `SOURCE_MANIFEST.txt` | No change: it records RELION provenance; nothing NVIDIA is imported | A line only if NVIDIA sample-derived source is ever added, with the l.35/l.46 notice "This software contains source code provided by NVIDIA Corporation." |
| `NOTICE` file | Not needed | Required for bundled `libnvcomp`: NVIDIA notices plus the third-party texts in nvCOMP `NOTICE` |
| `--help`/build output | Optional: `Found nvCOMP` status line already printed at configure | — |

### 3.5 D2 options

| Option | What it means | Risks / costs |
|---|---|---|
| **A. Keep optional, off, not vendored; add notice; distribute no linked binaries** (current nvCOMP practice, made explicit) | README paragraph (3.4). Release artefacts, if any, built with `USE_NVCOMP=OFF`. nvTIFF, if ever integrated, follows exactly the same pattern. | S3/S4 risk is left to third parties and named in the notice. A second optional SDK doubles the notice and test matrix. nvTIFF's Beta/pre-release status remains open. |
| **B. A, and allow project-distributed linked binaries** | e.g. a container with nvCOMP | S3/S4 conflict on both licences. Not supportable without counsel. |
| **C. Exclude proprietary optional dependencies beyond the CUDA toolkit** | Remove `USE_NVCOMP`; close the nvTIFF route | Loses the nvCOMP route: about 0.34 s/movie on Deflate input (section 4.4). LZW stays on LibTIFF. GPL-compatible replacement is a project-owned device decoder (as #193 option 2 for EER, or the device LZW decoder mentioned in #141). |
| **D. Ask before deciding** | Write to `nvidia-compute-license-questions@nvidia.com` (both agreements name it) and/or institutional counsel about S1–S4 and nvTIFF's pre-release status | Delay. Answers may not arrive before freeze; A remains the holding position. |

**Safe without a decision:** keep `USE_NVCOMP` OFF and unvendored; keep CI and any RC0
artefacts nvCOMP-free; keep nvTIFF off main (#152 stays a draft experiment); add the
factual README paragraph in 3.4, which describes current practice and commits to nothing new.

**Recommendation (maintainer decision):** A for nvCOMP. For nvTIFF, A at most, and only after
the pre-release question is answered (option D); until then it stays out of main.

## 4. D1 — the #134 trust boundary

### 4.1 How main routes a TIFF

`motioncorr_runner.cpp:2282–2317`. Under `--ingest auto` (default) or `--ingest nvcomp`, on a
`USE_NVCOMP=ON` build with a resident session, non-EER, non-compressed-MRC, the runner calls
`CudaMovieSession::ingestMovie` (`cuda_movie_session.cu:1189`), which calls
`ingestCompressedTiffStrips` (`:1385`). Its outcome maps to:

- `Success`: device movie used.
- `NotApplicable` (declined, no CUDA error): auto continues to compact (u8/u16 TIFF) or float;
  pinned `nvcomp` fails the movie (`runner:2313`).
- `RecoverableFailure` (CUDA error, context not poisoned): auto re-reads with the host reader,
  which overwrites `d_Iframes`/`d_Isum` in full (`runner:2302–2309`); pinned fails.
- `FatalDeviceFailure` (poisoning code latched in `CudaFailureState`): run fails, no fallback,
  no re-dispatch (`runner:2295–2300`).

Admitted encoding (`:1414–1458`): native byte order, `PREDICTOR_NONE`, `SAMPLEFORMAT_UINT`,
`FILLORDER_MSB2LSB`, geometry equal to the session's, 16 bits, 1 sample, contiguous planar,
Deflate/Adobe-Deflate, exactly `ny` strips of `nx*2` bytes. Every other encoding is declined
by name. #186 witnessed `nvcomp` for the tutorial, so the tutorial is on the auto nvCOMP route
on such builds (the corpus "u8" label is being checked by W-TIFF, #198).

### 4.2 Category table (main `1db86902`)

| #134 category | Main's behaviour | Code | Existing native evidence |
|---|---|---|---|
| Unsupported valid encoding (u8, multi-row strips, predictor, byte-swapped, LZW, …) | **Rejected before the library.** Tag-only scan, named decline, `NotApplicable`; auto → compact/float; pinned → movie fails | `cuda_movie_session.cu:1414–1481`; `runner:2313` | No dedicated decline fixture on main is cited here. Pinned-route refusal is exercised by `CudaNvcompReconstructionFailures` (`CMakeLists.txt:696–702`); compact vs nvcomp product identity in `docs/nvcomp_ingest_pipeline.md` |
| Truncated / incomplete TIFF: IFD chain | **Host reader fails the movie** before any route (`Corrupted TIFF directory structure`) | `rwTIFF.h:69–81` | Route-independent host checks |
| Truncated / incomplete TIFF: strip data beyond EOF | **Rejected before the library.** `pread`/`TIFFReadRawStrip` short read refuses the chunk (no log line); `NotApplicable`; auto host reader then reads the same file | `:1819`, `:1826`, `preadFully` `:1349` | No dedicated native fixture recorded |
| Truncated / incomplete TIFF: file still growing or replaced | **Not detected.** Tags are read in pass A; bytes are read later through fresh handles. No size/inode/mtime pin. The runner's recovery comment assumes "the immutable file" | `:1414` vs `:1749–1762`; `runner:2302–2307` | None |
| Invalid wrapper / offset / size | **Rejected before the library.** Raw size `< 7` or `> 4 GiB` refused (`:1463`); strip count/size must match one full row (`:1452`); zlib CMF/FLG/FCHECK/FDICT checked on the staged bytes with a named warning (`cuda_deflate_layout.h:47`, call `:1835`); compressed pointers alignment-checked (`:1692`); output capacity per strip is fixed at `row_bytes`, and nvCOMP documents an overflow status for undersized output | as listed | Host `DeflateLayout` tests; native 55/55 at `c4dad3b` (`docs/nvcomp_ingest_pipeline.md`) |
| Structurally corrupt Deflate body | **Submitted to nvCOMP.** Nothing validates the body before decode (the wrapper check reads two bytes). If nvCOMP reports a bad status or wrong length, the chunk is rejected before any output is consumed → `NotApplicable` → auto host reader / pinned fail. If nvCOMP misbehaves, the outcome is undefined: a sticky CUDA error becomes `FatalDeviceFailure`; a silent out-of-bounds write is not detectable | decode `:1934`; gate `:1871–1883` | **None.** #151 and the 5 October acceptance used healthy compressed input with injected readback; no corrupt-stream test exists |
| Valid Deflate, wrong Adler-32 trailer | **Detected after decode.** Device Adler-32 over each strip, read only for strips whose status and length passed; host checks all status/length first, then Adler; the gain kernel for that chunk is not launched → auto host reader / pinned fail | Adler kernel `:1944`; check `:1885–1893`; gain `:1963` | 5 Oct native acceptance, composition `50a59b5`, VM GPU0: CPU 34/34, CUDA-noNV 42/42, CUDA-NV 45/45, mutants fail as intended (#134); PR #151: 52/52, 13 CUDA, three compiled mutants discriminate. Both inject readback values; a real trailer-mutated file is not recorded |
| Resource failure | Arena or pinned-cap shortfall, or busy Fourier buffer: **named decline before allocation** (`:1527`, `:1562`, `:1679`) → host route. A CUDA allocation/copy error: `HANDLE_ERROR` records it → `RecoverableFailure` → auto host re-read / pinned fail | as listed; `ingestMovie` `:1220–1248` | Native 55/55 at `c4dad3b` incl. `CudaPreprocessingFailurePaths`, `CudaNvcompReconstructionFailures` |
| Fatal device / context failure | **Worker failure.** Poisoning code → `FatalDeviceFailure` → `REPORT_ERROR`, no CPU fallback, no re-dispatch | `ingestMovie` `:1200`, `:1222–1226`; `runner:2295–2300`; `cuda_failure_state.h` | `CudaPreprocessingFailurePaths`; `CudaErrorClass` (`tests/cuda_error_class.cpp`) |

Summary: every category except "structurally corrupt Deflate" and "growing file" is either
declined before nvCOMP or caught before any decoded byte is consumed. Those two are what D1
is about.

### 4.3 Options

| | (1) Trusted/immutable-input precondition for auto | (2) GPU decoder only on explicit opt-in | (3) Full CPU inflate before GPU decode |
|---|---|---|---|
| Behaviour | Unchanged. Documented: auto on a `USE_NVCOMP=ON` build is for complete, unmodified acquisition files; use `--ingest compact` for files of unknown integrity or still being written | Auto never calls nvCOMP; compact (u8/u16) and float remain automatic. nvCOMP runs only when the user asks | Every staged strip is inflated on the CPU (zlib, into scratch) and must end exactly at `Z_STREAM_END` with `row_bytes` out and a matching Adler before the batch is submitted |
| What it guarantees | Honest description; no new safety. The `USE_NVCOMP=OFF` default already makes nvCOMP a build-time choice | Malformed-input exposure only for users who opted in at run time | nvCOMP only sees syntactically valid streams whose output fits the buffer, i.e. inside its documented contract |
| What it does not | Corrupt or adversarial files still reach nvCOMP on such builds | Opt-in users keep the residual risk | Not a proof that nvCOMP is bug-free on valid input |
| Runtime cost (existing evidence) | 0 | On `USE_NVCOMP=ON` builds, Deflate movies return to compact: about **+0.34 s/movie** (u16 Deflate 8 rows/strip, compact 0.810 vs nvcomp 0.471 s/movie, #141). Tutorial, 24 movies: `--ingest compact` 20.9/21.0 s vs `--ingest nvcomp` 12.8/12.6 s, **≈ +0.35 s/movie** (`docs/single_gpu_execution_profile.md` §8, earlier candidate binary) | Adds roughly a host Deflate decode: **≈ 0.27 s/movie** (u16 Deflate 8 rows/strip, 1.61 s per 6 movies, instrumented, #141), removing most of the 0.34 s saving. The 8-CPU lane is already saturated while decoding (CPU/wall 3.2–4.7, #141). After a full CPU inflate the samples are already on the host, so this is close to the compact route plus a redundant GPU decode. Unmeasured |
| Effect on #138 (u8 and multi-row strips newly reach nvCOMP) | Population grows under the same precondition | Widening applies only to opt-in runs; no default change | Validation cost scales with the widened population |
| Effect on a future nvTIFF LZW route | Would need its own precondition, and trusts nvTIFF's TIFF parsing as well as its decode | Opt-in only; the PR #152 probe already requires `--trusted-input` | A CPU LZW validation is the LibTIFF decode nvTIFF exists to remove (0.3–2.6 s/movie): no gain left |

**Project-owned device decoders (#193 option 2, a possible device LZW decoder).** These differ
in kind. With our own GPL kernel we control every read and write: each fraction or code
stream has a known length, every run or code advance can be checked against the frame or strip
size before the write, and violations set a per-unit error flag that the host checks before
consumption. Behaviour on malformed input is then ours to specify, test with mutated and
truncated fixtures, and audit in source; no vendor undefined-behaviour clause applies. The
#134 categories still have to be answered and tested for it, but D1's options 1–3 exist only
because nvCOMP's (and nvTIFF's) internals are closed. D1 need not block the EER prototype.

### 4.4 Cost reference

| Quantity | Value | Source |
|---|---|---|
| Compact-route host LibTIFF decode, LZW | 0.305 s/movie (u8), 0.428 s/movie (u16) | #141, 2 Oct, instrumented |
| Compact → nvcomp, u16 Deflate 8 rows/strip | 0.810 → 0.471 s/movie (−0.339) | #141 / #138 campaign |
| Tutorial 24 movies, compact vs nvcomp | 20.9/21.0 s vs 12.8/12.6 s | `docs/single_gpu_execution_profile.md` §8 |
| Host Deflate decode, u16 8 rows/strip | 1.61 s per 6 movies (≈ 0.27 s/movie) | #141, 2 Oct, instrumented |
| Real LZW compact host read | 1.39 / 2.61 / 0.70 s/movie (10361 / 10441 / 10641) | #141, 16 Oct, #186 GPU pass |

### 4.5 Recommendation (maintainer decision)

**Option 1 for the existing u16 one-row-per-strip auto route; option 2 for any population
not admitted on main today** (#138's u8 and multi-row encodings, nvTIFF).

Rationale:

- The existing route is in released behaviour, is reached only on builds where someone chose
  `USE_NVCOMP=ON`, and is worth about 0.35 s/movie on the tutorial. Every category other than a
  corrupt Deflate body or a changing file is already handled before consumption (4.2). The
  realistic threat for acquisition data is transfer damage, which the status, length and
  Adler gates catch whenever nvCOMP reports honestly; the residual risk is decoder misbehaviour
  on a damaged body. Stating that plainly is cheaper than removing the route.
- Widening is new exposure. Gating it behind opt-in keeps "nothing weakened relative to the
  released fast path" (PR #138's own claim) true for the default, and lets #138's measured
  gains be used by sites that accept the boundary.
- Option 3 is dominated on the evidence: it costs about what it saves.
- The #134 owner earlier recommended option 2 throughout (#134, 2 Oct). That is the stronger
  claim, at about +0.35 s/movie on Deflate input for `USE_NVCOMP=ON` builds. If the
  maintainer prefers a single rule, option 2 everywhere is the consistent alternative.

If no decision is made before freeze: the existing route stays as it is (it is current main),
the factual limitation text below should still ship, T1 (#138) stays HOLD, L1 stays NO-GO.

### 4.6 Exact changes each option implies

Common to all options (documentation only):

- `README.md`: an "Input trust" paragraph quoting the vendor limitation (2.1) and naming
  `--ingest compact` as the route that keeps every TIFF on LibTIFF.
- `docs/input_backends/FAILURE_POLICY.md` on main: the category table of 4.2, adapted from
  PR #138's file to main's narrower admission.

Option 1:

- `motioncorr_runner.cpp:157` `--ingest` help: add "auto may decode Deflate TIFF on the GPU
  (nvCOMP); use only on complete, unmodified files."
- Replace the "immutable file" assumption in the comment at `runner:2302–2307` with a reference
  to the documented precondition.
- Optional hardening, small code change: record `fstat` (`st_dev`, `st_ino`, `st_size`,
  `st_mtim`) on the pass-A handle, compare on each reader handle (`:1749–1762`) and after the
  last chunk read; decline with a named message on mismatch. Add a CTest that rewrites the file
  between passes via the existing shim. This addresses #134 item 2 (growing file), not decoder
  safety.
- Add log lines for the silent refusals (`:1463`, short read at `:1819`/`:1826`) so a truncated
  strip is distinguishable from an unsupported encoding.

Option 2:

- `motioncorr_runner.cpp:2283`: call `ingestMovie` only when nvCOMP was requested.
  - 2a: reuse `--ingest nvcomp`. An ineligible movie in a mixed dataset then fails, by the
    existing pin semantics.
  - 2b: add an explicit opt-in that keeps auto's fallback (for example `--ingest nvcomp_or_host`
    or a separate `--trust_gpu_decoder`), so mixed datasets still complete.
- Update `--ingest` help, README, and any test, harness or benchmark recipe that expects the
  `nvcomp` witness under the default (`--ingest_witness`). The tutorial benchmark recipes in
  `docs/` that rely on auto selecting nvCOMP would need `--ingest nvcomp`.
- Hybrid (recommended): keep auto's current admission at `cuda_movie_session.cu:1414–1458`
  unchanged, and admit #138's widened encodings only on the opt-in path.

Option 3:

- In `read_chunk` (`:1780–1866`), after the wrapper check, inflate each staged strip on the
  reader thread into per-thread scratch with zlib; require `Z_STREAM_END`, exactly `raw_sz`
  consumed, `row_bytes` produced; decline the batch otherwise. Validate the same pinned bytes
  that are uploaded, so the check and the decode see one snapshot.
- A matched current-main A/B (tutorial and #138 variants, ≥3 pairs, null control) before
  adoption, per #134 item 5.

## 5. nvTIFF promotion checklist (#141 gates)

| Gate | Status | Evidence |
|---|---|---|
| Standalone decode identity | **PASS** (scope: controlled U8/U16 LZW; real U8 LZW) | PR #152: 143,661,056 controlled samples exact; 13 Oct: 10,936,442,880 real U8 samples exact on SCARF and VM (5 movies) |
| ≥ 0.15 s/movie saving | **SCARF PASS**, mean 0.89 s/movie (ingest-ready 0.891 [0.883, 0.898], checked-exit 0.890 [0.878, 0.912]; per file 0.51–1.71; null max 0.052/0.081). **VM UNRESOLVED** (aborted on the 0.25 unowned-core gate; 2 of 5 files complete). Standalone ingest, warm cache, U8 only | `experiment/nvtiff-timing-20261016` `RESULT.md` (SCARF job 3633126) |
| Scratch / VRAM | Callback runs: 3.21–14.11 MiB device, 64.19–192 KiB pinned high-water; sampled extra owned GPU memory +8 to +18 MiB. Not a hard bound and not whole-application VRAM | #141, 13 Oct |
| Malformed-LZW safety | **Unproven.** Vendor header documents TIFF-structure errors only (2.2). Fault injections used healthy streams | PR #152 `NATIVE_RESULTS.md` |
| Real U16 LZW | Not covered | #141 |
| Licence (D2) | **Open**, plus pre-release/Beta question (3.3) | this brief |
| Trust policy (D1) | **Open**; under the recommendation, nvTIFF would be opt-in only | this brief |
| Complete-product integration gate | **Not started.** Needs: TIFF→MRC row flip and gain orientation re-established against nvTIFF output (#60 precedent: unflipped re-encode relRMSE 1.435, flip-only 0.700); frame selection (`--first_frame_sum`/`--last_frame_sum`, IFD-offset regions); full MRC header/payload and STAR identity against the compact route on the release baseline; failure and no-publication on decoder refusal, execution failure and late failure; memory admission with nvTIFF scratch included; `--ingest_witness` value and a pinnable `--ingest` mode with refusal semantics | #141, PR #152 README "Contract" |

**nvTIFF integration is not in RC0** unless, before freeze, D1 and D2 both permit it **and** the
complete-product integration gate above passes on the RC0 baseline. Neither decision is made
and the gate has not started, so the #198 register entry L1 (NO-GO for RC0 integration)
stands.

## 6. Open questions for the maintainer

1. D1: option 1, 2, 3, or the hybrid (1 for the existing route, 2 for widening)? Under option 2,
   reuse the pin (2a) or add a fallback-preserving opt-in (2b)?
2. D1: should the file-identity pin (4.6, option 1) be in RC0 scope, given it is a small source
   change after the "no new features" rule in #198?
3. D2: accept A for nvCOMP and add the README notice now?
4. D2: will the project ever distribute binaries (containers, conda, modules)? If yes, counsel
   is needed before any is built with nvCOMP or nvTIFF.
5. nvTIFF: ask NVIDIA whether 0.8.0.82 (`Development Status :: 4 - Beta`) is "pre-release"
   under the agreement, before spending on the integration gate?
6. If nvTIFF is excluded, is a project-owned device LZW decoder in scope after RC0, using the
   same bounds-checked design as #193 option 2?

## Provenance of this brief

- Repository reads at `1db86902`; branch inputs read from `origin/experiment/nvtiff-lzw-20261002`
  (`d61308a2`), `origin/experiment/nvtiff-timing-20261016`, `origin/experiment/input-nvcomp-widen`.
- Vendor files read on 4GPUs (commands pinned with `taskset -c 64-67`) and on the SCARF login
  node, read-only. No motioncorr run, benchmark or job was started; nothing was modified on
  either host. Vendor text is quoted, not copied into the repository.
