# RC0 decision brief: decoder trust boundary (D1) and proprietary optional dependencies (D2)

Coordination: #198 (D1, D2, T1, T2, L1). Inputs: #134, #141, #193, PR #138, PR #151, PR #152,
`experiment/nvtiff-timing-20261016`. Source revision read: `main` =
`1db869025507ac801845b4001b84e6bc0e77a645`. This is a documentation brief. It changes no
source and decides nothing; each option below is for the maintainer to choose.

**Section 3 is not legal advice. Licence compatibility is a maintainer decision.**

## 1. Summary

| | Current state | Options | Brief's recommendation |
|---|---|---|---|
| D1 | `--ingest auto` on a `USE_NVCOMP=ON` build sends eligible u16 one-row-per-strip Deflate TIFF strips to nvCOMP. NVIDIA documents undefined behaviour for corrupt input. Main's checks are output-integrity checks; nothing validates the Deflate body before the decoder runs. In the #186 corpus only the tutorial takes this route. | Uniform (1): documented trusted/immutable-input precondition for auto, all nvCOMP-eligible encodings. Uniform (2): GPU decoder only on explicit opt-in (for RC0, only by reusing the `--ingest nvcomp` pin). (3) full CPU inflate before GPU decode: current cost unmeasured | Uniform option 1 for RC0, because it needs no source change; the evidence supports uniform option 2a equally. Section 4.5. |
| D2 | nvCOMP is `option(USE_NVCOMP OFF)`, found with `find_library`, never vendored; CI builds without it; the project distributes no binaries. nvTIFF exists only on unmerged branch #152. | A: keep optional/off/not vendored, add a notice, distribute no linked binaries; B: also distribute linked binaries; C: exclude proprietary optional dependencies; D: ask NVIDIA / counsel first | A for nvCOMP. Section 3.5. |
| nvTIFF | Standalone decode exact; SCARF timing GO (0.89 s/movie); VM unresolved; malformed-LZW safety unproven; no application route | — | **NO-GO for RC0.** The complete-product gate has not started and cannot realistically pass before freeze; S3/S4 licensing is unresolved. Reconsider after RC0 if D1/D2 permit. Section 5. |

### 1.1 RC0 freeze matrix

Minimal change set before freeze for each likely outcome. "QF rerun" means the frozen-SHA
qualification in #198 must be repeated because source changed.

| Outcome | Source changes | Doc changes | QF rerun? | T1 (#138) / L1 (nvTIFF) |
|---|---|---|---|---|
| Uniform 1 + D2 A | **None** | README "Input trust" and "Optional proprietary dependencies" paragraphs; `docs/input_backends/FAILURE_POLICY.md` for main | No | T1 HOLD (or merge under the same rule only if qualified before QF); L1 NO-GO |
| Uniform 2a + D2 A | `runner:2283`: call `ingestMovie` only under `INGEST_NVCOMP`; `--ingest` help text (`runner:157`) | As above, plus "auto does not use nvCOMP"; tutorial benchmark recipes pass `--ingest nvcomp` | **Yes** (route selection changed; tests expecting the `nvcomp` witness under auto must be updated) | T1 HOLD; L1 NO-GO |
| No decision before freeze | **None** | Factual vendor-limitation and dependency notices only (same text as uniform 1 minus the precondition wording) | No | T1 HOLD; L1 NO-GO |

The doc changes are still changes: they need review like any other RC0 documentation, but
they do not alter numerical results, routing or defaults. Optional source additions (per-run
nvCOMP log notice, file-identity check, bounds-audit fixes) are not in any minimal set; each
would require a QF rerun (sections 4.2.1 and 4.3.1; questions 2–4 in section 6).

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
- **nvTIFF: secondary pre-release question.** The wheel declares `Development Status :: 4 - Beta`
  and version 0.8. The agreement says pre-release SDKs "are not intended for use in
  production or business-critical systems" (nvTIFF l.60). That sentence sits in a
  risk/warranty clause addressed to the SDK user; it is not the primary blocker. nvTIFF's
  exclusion from RC0 rests on the unstarted complete-product gate (section 5) and on the same
  S3/S4 question as nvCOMP. Whether the classifier "identifies" the release as pre-release is
  for NVIDIA or counsel, and is a further reason not to integrate before a 1.0 release.
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
| **C. Exclude proprietary optional dependencies beyond the CUDA toolkit** | Remove `USE_NVCOMP`; close the nvTIFF route | Loses the nvCOMP route. On current main that affects only u16 one-row-per-strip Deflate TIFF (in the #186 corpus, the tutorial); the historical tutorial difference is ≈ 0.35 s/movie of process wall (section 4.4). LZW stays on LibTIFF. GPL-compatible replacement is a project-owned device decoder (as #193 option 2 for EER, or the device LZW decoder mentioned in #141). |
| **D. Ask before deciding** | Write to `nvidia-compute-license-questions@nvidia.com` (both agreements name it) and/or institutional counsel about S1–S4 and nvTIFF's pre-release status | Delay. Answers may not arrive before freeze; A remains the holding position. |

**Safe without a decision:** keep `USE_NVCOMP` OFF and unvendored; keep CI and any RC0
artefacts nvCOMP-free; keep nvTIFF off main (#152 stays a draft experiment); add the
factual README paragraph in 3.4. None of these changes defaults, routing or numerical
results, but they are not literally change-free: the README paragraph is a documentation
change needing review, and "nvCOMP-free RC0 artefacts" is a release constraint W-REL must
apply.

**Recommendation (maintainer decision):** A for nvCOMP. nvTIFF is NO-GO for RC0 (section 5);
if it is reconsidered after RC0, it could follow A at most, ideally after option D answers the
S3/S4 and pre-release questions.

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
- `FatalDeviceFailure` (poisoning code latched in `CudaFailureState`): that movie fails with no
  fallback or retry (`runner:2295–2300`). `run()` catches the error, records the failure and
  continues with the remaining movies in the same process (`runner:1045–1055`); at the end it
  fails the job and withholds joint STAR/PDF output (`runner:1083–1089`). This is not an
  immediate worker or process termination, and these citations do not establish a
  process-wide latch against later CUDA dispatch.

Admitted encoding (`:1414–1458`): native byte order, `PREDICTOR_NONE`, `SAMPLEFORMAT_UINT`,
`FILLORDER_MSB2LSB`, geometry equal to the session's, 16 bits, 1 sample, contiguous planar,
Deflate/Adobe-Deflate, exactly `ny` strips of `nx*2` bytes. Every other encoding is declined
by name.

**Population on main.** In the ten-family #186 corpus (`docs/workload_corpus/gpu/README.md`,
main `116eb04a`, `--ingest_witness` on every run), only the tutorial takes `nvcomp`. The three
real TIFF depositions (EMPIAR-10361, 10641, 10441) are u8 LZW BigTIFF on `compact`; the other
six families are EER or MRC on `float`. (The corpus labels the tutorial "u8"; W-TIFF is
checking that label, #198.) #138 would extend nvCOMP only to Deflate TIFF writers; it does not
touch LZW, EER or MRC.

### 4.2 Category table (main `1db86902`)

| #134 category | Main's behaviour | Code | Existing native evidence |
|---|---|---|---|
| Unsupported valid encoding (u8, multi-row strips, predictor, byte-swapped, LZW, …) | **Rejected before the library.** Tag-only scan, named decline, `NotApplicable`; auto → compact/float; pinned → movie fails | `cuda_movie_session.cu:1414–1481`; `runner:2313` | **No dedicated test** submits an unsupported encoding under `--ingest nvcomp` and asserts refusal. (`CudaNvcompReconstructionFailures` pins a *supported* fixture and is not refusal coverage.) Compact vs nvcomp product identity: `docs/nvcomp_ingest_pipeline.md` |
| Truncated / incomplete TIFF: IFD chain | **Host reader fails the movie** before any route (`Corrupted TIFF directory structure`) | `rwTIFF.h:69–81` | Route-independent host checks |
| Truncated / incomplete TIFF: strip data beyond EOF | **Rejected before the library.** `pread`/`TIFFReadRawStrip` short read refuses the chunk (no log line); `NotApplicable`; auto host reader then reads the same file | `:1819`, `:1826`, `preadFully` `:1349` | No dedicated native fixture recorded |
| Truncated / incomplete TIFF: file still growing or replaced | **Not detected.** Tags are read in pass A; bytes are read later through fresh handles. No size/inode/mtime pin. The runner's recovery comment assumes "the immutable file" | `:1414` vs `:1749–1762`; `runner:2302–2307` | None |
| Invalid wrapper / offset / size | **Ordinary cases rejected before the library.** Raw size `< 7` or `> 4 GiB` refused (`:1463`); strip count/size must match one full row (`:1452`); zlib CMF/FLG/FCHECK/FDICT checked on the staged bytes with a named warning (`cuda_deflate_layout.h:47`, call `:1835`); compressed pointers alignment-checked (`:1692`); output capacity per strip is fixed at `row_bytes`, and nvCOMP documents an overflow status for undersized output. **Arithmetic is not checked throughout; see 4.2.1.** | as listed | Host `DeflateLayout` tests; native 55/55 at candidate `c4dad3b` (`docs/nvcomp_ingest_pipeline.md`) |
| Structurally corrupt Deflate body | **Submitted to nvCOMP.** Nothing validates the body before decode (the wrapper check reads two bytes). If nvCOMP reports a bad status or wrong length, the chunk is rejected before any output is consumed → `NotApplicable` → auto host reader / pinned fail. If nvCOMP misbehaves, the outcome is undefined: a sticky CUDA error becomes `FatalDeviceFailure`; a silent out-of-bounds write is not detectable | decode `:1934`; gate `:1871–1883` | **None.** #151 and the 5 October acceptance used healthy compressed input with injected readback; no corrupt-stream test exists |
| Valid Deflate, wrong Adler-32 trailer | **Detected after decode.** Device Adler-32 over each strip, read only for strips whose status and length passed; host checks all status/length first, then Adler; the gain kernel for that chunk is not launched → auto host reader / pinned fail | Adler kernel `:1944`; check `:1885–1893`; gain `:1963` | 5 Oct native acceptance, composition `50a59b5`, VM GPU0: CPU 34/34, CUDA-noNV 42/42, CUDA-NV 45/45, mutants fail as intended (#134); PR #151 at `c596164`: 52/52, 13 CUDA, three compiled mutants discriminate. Both inject readback values; a real trailer-mutated file is not recorded |
| Resource failure | Arena or pinned-cap shortfall, or busy Fourier buffer: **named decline before allocation** (`:1527`, `:1562`, `:1679`) → host route. A CUDA allocation/copy error: `HANDLE_ERROR` records it → `RecoverableFailure` → auto host re-read / pinned fail | as listed; `ingestMovie` `:1220–1248` | Native 55/55 at candidate `c4dad3b` incl. `CudaPreprocessingFailurePaths`, `CudaNvcompReconstructionFailures` |
| Fatal device / context failure | **That movie fails; no fallback or retry for it.** Poisoning code → `FatalDeviceFailure` → `REPORT_ERROR`; `run()` continues the remaining movies, then fails the job and withholds joint output (4.1) | `ingestMovie` `:1200`, `:1222–1226`; `runner:2295–2300`, `1045–1055`, `1083–1089`; `cuda_failure_state.h` | `CudaPreprocessingFailurePaths`; `CudaErrorClass` (`tests/cuda_error_class.cpp`) |

Summary: apart from a corrupt Deflate body and a changing file, the categories are declined
before nvCOMP or caught before any decoded byte is consumed, **subject to the open bounds
audit in 4.2.1**. All native evidence above is integrity evidence on healthy input or injected
readbacks, not corrupt-Deflate safety and not current-head native qualification.

#### 4.2.1 Outstanding: checked-arithmetic bounds audit (#134 item 2)

The ordinary layout and capacity checks are real, but size and offset arithmetic is not
checked throughout. Sites identified by review (R-TRUST-A) and confirmed in source:

| Site | Unchecked operation |
|---|---|
| `cuda_movie_session.cu:1352`, `:1357` (`preadFully`) | `(off_t)offset` cast and `offset += got` with no representability or overflow guard |
| `cuda_movie_session.cu:1469` | contiguity test `raw_offsets[s-1] + raw_sizes[s-1]` can wrap |
| `cuda_movie_session.cu:1625–1657` | candidate sizing products (`candidate * alignUp(max_frame_stage, …)`, `chunks * row_bytes`, `chunks * row_pitch_bytes`, table sizes) |
| `cuda_deflate_layout.h:28–37` | `stripSlotOffset`/`frameStageBytes` alignment and running sums |
| `cuda_deflate_layout.h:72–73` | `pinnedReserveBytes`: `bytes + bytes/8` and round-up |
| `cuda_deflate_layout.h:156–176` | `pinnedChunkLayout` offset sums and table products |

The arena's subtraction-based capacity check cannot detect a size that wrapped before the
call. Mitigations exist: `initialize()` bounds frame pixel counts (`:451–455`), session
allocation must succeed, and the default 256 MiB pinned cap restricts reachable sizes. **No
end-to-end overflow reaching nvCOMP has been demonstrated**, and none is claimed here. Until the
audit is done, the brief does not claim universal rejection of invalid sizes or offsets.
Whether to do it before freeze is question 3 in section 6.

### 4.3 Options

The primary choices are **uniform**: one rule for every nvCOMP-eligible Deflate encoding,
whether or not #138 merges.

| | Uniform (1): trusted/immutable-input precondition for auto | Uniform (2): GPU decoder only on explicit opt-in | (3) Full CPU inflate before GPU decode |
|---|---|---|---|
| Behaviour | Unchanged. Documented: auto on a `USE_NVCOMP=ON` build is for complete, unmodified acquisition files; use `--ingest compact` for files of unknown integrity or still being written | Auto never calls nvCOMP; compact (u8/u16) and float remain automatic. For RC0, the only opt-in is the existing pin **`--ingest nvcomp` (2a)**: a movie that cannot take nvCOMP fails, per `runner:157` and `:2313`. A fallback-keeping opt-in (2b, e.g. `--ingest nvcomp_or_host`) is new CLI surface and belongs after RC0 | Every staged strip is inflated on the CPU (zlib, into scratch) and must end exactly at `Z_STREAM_END` with `row_bytes` out and a matching Adler before the batch is submitted |
| What it guarantees | Honest description; no new safety. `USE_NVCOMP=OFF` by default already makes nvCOMP a build-time choice | Malformed-input exposure only for runs that pinned nvCOMP | nvCOMP only sees syntactically valid streams whose output fits the buffer, i.e. inside its documented contract |
| What it does not | Corrupt or adversarial files still reach nvCOMP on such builds | Opt-in runs keep the residual risk. Under 2a a mixed dataset (some movies ineligible) fails under the pin | Not a proof that nvCOMP is bug-free on valid input |
| Runtime cost | 0 | On current main only u16 one-row-per-strip Deflate is affected (the #138 8-row population is already rejected by main, so its cost is zero). The only evidence for the affected population is historical: tutorial 24-movie **process wall**, `--ingest compact` 20.9/21.0 s vs `--ingest nvcomp` 12.8/12.6 s, from an earlier candidate binary (≈ 0.34–0.35 s/movie). **Current-main penalty unmeasured** | **Unmeasured.** The nearest figure, ≈ 0.27 s/movie, is an instrumented LibTIFF compact-reader stage on #138's 8-row variant, not a zlib validator on staged bytes. Expectation only: since a full CPU inflate leaves the samples on the host, the route would cost roughly what compact costs plus a redundant GPU decode |
| Freeze impact | None | Source change at `runner:2283`; QF rerun | Source change in `read_chunk`; A/B required; QF rerun |
| Effect on #138 (u8 and multi-row strips newly reach nvCOMP) | Same precondition covers the widened population if #138 merges | Widening applies only to pinned runs | Validation cost scales with the widened population |
| Effect on a future nvTIFF LZW route | Would need the same precondition, and trusts nvTIFF's TIFF parsing as well as its decode | Opt-in only; the PR #152 probe already requires `--trusted-input` | A CPU LZW validation is the LibTIFF decode nvTIFF exists to remove (0.70–2.61 s/movie on the real corpus, #141): expected to leave little or no gain (unmeasured) |

#### 4.3.1 Considered and not proposed for RC0

- **Hybrid** (uniform 1 for the existing u16 one-row route, 2 for #138's widening and nvTIFF;
  recommended in revision `c34a6024`). Objection (R-TRUST-B): the same vendor undefined
  behaviour applies to every Deflate encoding; routing two files from one microscope
  differently because `RowsPerStrip` is 1 or 8 is opaque, hard to document, and adds a
  qualification axis. Counter-argument: only the narrow population is released behaviour, so
  the hybrid keeps "nothing weakened relative to the released fast path" true for the default.
  For a release that must be documented and qualified, the objection is stronger.
- **Bit-level structural pre-checks** (find the final block's `BFINAL`/`BTYPE`, bound output
  from headers). Deflate blocks are bit-packed; their boundaries and lengths are known only
  after decoding every Huffman symbol in order, so a check strong enough to validate the body
  is a full decode (option 3). The two-byte zlib wrapper check is the cheap limit.
- **Process isolation** (decode in a separate worker). The decoded movie must reach the main
  context through CUDA IPC or a host round trip, with new worker lifecycle and failure
  handling: an architectural change, outside RC0's "no new architectures" rule.
- **Per-run log notice under option 1.** The movie log already records the route on success
  (`nvCOMP ingestion: chunk=…`, `:1696`) and `--ingest_witness` records it when asked; neither
  states the precondition. A one-line notice when auto first takes nvCOMP is a small source
  change; it changes log bytes (output-tree comparisons may need an allowance) and requires a
  QF rerun. Optional.
- **Build-time default policy** (a CMake switch for whether auto may use nvCOMP): new
  configure surface; after RC0 if wanted.
- **File-identity check** (`fstat` `st_dev`/`st_ino`/`st_size`/`st_mtim` pinned at pass A,
  rechecked on every reader handle and after the last read). Orthogonal to options 1–3: it
  closes the growing/replaced-file gap, not decoder safety. Recommendation: defer past RC0 and
  rely on the documented precondition, unless the maintainer opens a bug-fix lane (source
  change, CTest, QF rerun).

**Project-owned device decoders (#193 option 2; a possible device LZW decoder)** differ in
kind: we own every read and write, can check each run or code advance against the frame or
strip size before writing, and can flag violations per unit for the host to check before
consumption. Malformed-input behaviour is then ours to specify, test with mutated and
truncated fixtures, and audit; no vendor undefined-behaviour clause applies. The #134
categories still need answers and tests, but D1 need not block the EER prototype.

### 4.4 Cost reference

All figures are historical; none is a measurement on `1db86902`.

| Quantity | Value | Endpoint, population, source |
|---|---|---|
| Tutorial 24 movies, compact vs nvcomp | 20.9/21.0 s vs 12.8/12.6 s (≈ 0.34–0.35 s/movie) | 24-movie process wall, earlier candidate binary, same binary with the route forced; u16 one-row Deflate (the population main admits). `docs/single_gpu_execution_profile.md` §8 |
| Compact → nvcomp, u16 Deflate 8 rows/strip | 0.810 → 0.471 s/movie (−0.339) | Median movie-log wall after movie 1, `main` then `c499b1d`; **#138's widened route, rejected by main**. #141 / PR #138 `RESULTS.md` |
| Host LibTIFF Deflate stage, u16 8 rows/strip | 1.61 s per 6 movies (≈ 0.27 s/movie) | Instrumented compact-reader stage, not comparable with production walls; not a zlib validator. #141, 2 Oct |
| Compact-route host LibTIFF decode, LZW | 0.305 s/movie (u8), 0.428 s/movie (u16) | Instrumented stage, controlled fixtures. #141, 2 Oct |
| Real LZW compact host read | 1.39 / 2.61 / 0.70 s/movie (10361 / 10441 / 10641) | `host read movie` stage, main `116eb04a`, #186 GPU pass. #141, 16 Oct. CPU/wall 3.2–4.7 there; that ratio alone does not establish saturation of the eight CPUs |

Population impact: on main, and across the #186 corpus, only the tutorial uses nvCOMP, so the
cost of uniform option 2 falls on Deflate TIFF workflows and tutorial benchmarks, not on the
LZW, EER or MRC families.

### 4.5 Recommendation (maintainer decision)

**The evidence supports either uniform rule.** If one is wanted for RC0, **uniform option 1**,
because it is the outcome that needs no source change and no QF rerun (section 1.1).

- For uniform 1: main's behaviour is unchanged; the route is reached only on builds where
  someone chose `USE_NVCOMP=ON`, which is already a site-level opt-in; in the corpus only the
  tutorial is affected. The realistic threat for acquisition data is transfer damage, which the
  status, length and Adler gates catch whenever nvCOMP reports honestly; the residual risk is
  decoder misbehaviour on a damaged body, which the precondition states plainly. #138 could
  later enter under the same rule once its own qualification passes.
- For uniform 2a: it is the stronger safety claim (the #134 owner recommended option 2 on
  2 Oct), it reuses the existing pin contract with no new CLI surface, and its cost falls only
  on u16 one-row Deflate users. Against it: a source change and QF rerun before freeze, an
  unmeasured current penalty, and hard failure of mixed datasets under the pin.
- Option 3 is not recommended for RC0: its cost is unmeasured, and the expectation above
  suggests little advantage over compact.

If no decision is made before freeze: main stays as it is, the factual limitation text ships,
T1 (#138) stays HOLD, L1 stays NO-GO (section 1.1).

### 4.6 Exact changes each option implies

Section 1.1 gives the minimal set per outcome. Detail:

- **All outcomes (documentation):** `README.md` "Input trust" paragraph quoting the vendor
  limitation (2.1) and naming `--ingest compact` as the route that keeps every TIFF on
  LibTIFF; `docs/input_backends/FAILURE_POLICY.md` on main with the 4.2 table and 4.2.1 status.
- **Uniform 1:** the README states the precondition (complete, unmodified acquisition files).
  No source change is required. Optional, each a source change with a QF rerun: `--ingest`
  help wording (`runner:157`); the per-run notice (4.3.1); log lines for the silent refusals
  (`:1463`, short reads `:1819`/`:1826`); the "immutable file" comment at `runner:2302–2307`
  pointing to the precondition.
- **Uniform 2a:** `runner:2283` calls `ingestMovie` only when `ingest_mode == INGEST_NVCOMP`;
  help text and README say auto does not use nvCOMP and `--ingest nvcomp` opts in with strict
  refusal; tests, harnesses and `docs/` tutorial recipes that expect the `nvcomp` witness under
  the default pass `--ingest nvcomp`; QF rerun. 2b is out of RC0 scope.
- **Option 3:** in `read_chunk` (`:1780–1866`), after the wrapper check, inflate each staged
  strip with zlib into per-thread scratch; require `Z_STREAM_END`, exactly `raw_sz` consumed and
  `row_bytes` produced; decline otherwise. Validate the same pinned bytes that are uploaded.
  Requires a matched current-main A/B (≥3 pairs, null control) per #134 item 5, then QF.

## 5. nvTIFF promotion checklist (#141 gates)

| Gate | Status | Evidence |
|---|---|---|
| Standalone decode identity | **PASS** (scope: controlled U8/U16 LZW; real U8 LZW) | PR #152: 143,661,056 controlled samples exact; 13 Oct: 10,936,442,880 real U8 samples exact on SCARF and VM (5 movies) |
| ≥ 0.15 s/movie saving | **SCARF PASS**, mean 0.89 s/movie (ingest-ready 0.891 [0.883, 0.898], checked-exit 0.890 [0.878, 0.912]; per file 0.51–1.71; null max 0.052/0.081). **VM UNRESOLVED** (aborted on the 0.25 unowned-core gate; 2 of 5 files complete). Standalone ingest, warm cache, U8 only | `experiment/nvtiff-timing-20261016` `RESULT.md` (SCARF job 3633126) |
| Scratch / VRAM | Callback runs: 3.21–14.11 MiB device, 64.19–192 KiB pinned high-water; sampled extra owned GPU memory +8 to +18 MiB. Not a hard bound and not whole-application VRAM | #141, 13 Oct |
| Malformed-LZW safety | **Unproven.** Vendor header documents TIFF-structure errors only (2.2). Fault injections used healthy streams | PR #152 `NATIVE_RESULTS.md` |
| Real U16 LZW | Not covered | #141 |
| Licence (D2) | **Open**: S3/S4 question as for nvCOMP; secondary pre-release/Beta question (3.3) | this brief |
| Trust policy (D1) | **Open**; under uniform 1 it needs the same precondition plus trust in nvTIFF's TIFF parser; under uniform 2 it is pinned opt-in only | this brief |
| Complete-product integration gate | **Not started.** Needs: TIFF→MRC row flip and gain orientation re-established against nvTIFF output (#60 precedent: unflipped re-encode relRMSE 1.435, flip-only 0.700); frame selection (`--first_frame_sum`/`--last_frame_sum`, IFD-offset regions); full MRC header/payload and STAR identity against the compact route on the release baseline; failure and no-publication on decoder refusal, execution failure and late failure; memory admission with nvTIFF scratch included; `--ingest_witness` value and a pinnable `--ingest` mode with refusal semantics | #141, PR #152 README "Contract" |

**Recommendation: nvTIFF is NO-GO for RC0.** Primary reasons: the complete-product
integration gate has not started and cannot realistically pass before freeze, and the S3/S4
licensing question (3.3) is unresolved. The Beta/pre-release clause is a secondary reason.
This matches #198 register entry L1. Reconsider after RC0 if D1 and D2 permit it; the
standalone and SCARF timing evidence above remains valid input for that decision.

## 6. Open questions for the maintainer

1. D1: uniform option 1, uniform option 2a, or option 3? (For RC0, option 2 means reusing
   `--ingest nvcomp` with strict refusal; a fallback-keeping opt-in is post-RC0.)
2. D1: open a bug-fix lane for the file-identity check before freeze, or defer it past RC0 as
   this brief recommends (4.3.1)?
3. D1: the checked-arithmetic bounds audit (4.2.1): RC0 hardening (source change, QF rerun) or
   post-RC0?
4. D1 under option 1: add the optional per-run trust notice (source change, QF rerun), or
   documentation only?
5. D2: accept A for nvCOMP and add the README notice now?
6. D2: will the project ever distribute binaries (containers, conda, modules)? If yes, counsel
   is needed before any is built with nvCOMP or nvTIFF.
7. nvTIFF after RC0: ask NVIDIA about S3/S4 and whether 0.8.0.82 (`Development Status :: 4 -
   Beta`) is "pre-release" under the agreement, before spending on the integration gate?
8. If nvTIFF is excluded, is a project-owned device LZW decoder in scope after RC0, using the
   same bounds-checked design as #193 option 2?

## Provenance of this brief

- Revision 2 addresses review R-TRUST-A (PR #199 review 5552919790) and R-TRUST-B (PR #199
  comment 6223436930). Revision 1 was `c34a6024`.
- Repository reads at `1db86902`; branch inputs read from `origin/experiment/nvtiff-lzw-20261002`
  (`d61308a2`), `origin/experiment/nvtiff-timing-20261016`, `origin/experiment/input-nvcomp-widen`.
- Vendor files read on 4GPUs (commands pinned with `taskset -c 64-67`) and on the SCARF login
  node, read-only. No motioncorr run, benchmark or job was started; nothing was modified on
  either host. Vendor text is quoted, not copied into the repository.
