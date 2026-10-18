# RC0 release checklist (DRAFT, stays DRAFT until the freeze)

Status: **draft, pre-freeze, revision 7** (after the R-REL review of PR #201, the 11:54Z review of revision 6, and the maintainer decisions D1, D2, T3, D4, D5, D6, D7, D10, D12, D13 and D14). This checklist is for an **evaluation RC0**, not a stable release (D7). Commands below were written against main `1db86902` and re-checked on later merges; **source line numbers are at main `cb3699ac`** and must be re-checked against F. Each command is tagged:

- **LOCAL-OK**: run on macOS arm64 (AppleClang, Homebrew) in this worktree for this draft; result stated.
- **UNRUN**: not executed. Linux/CUDA commands are UNRUN until the final qualification (**QF**, #198) runs them.

Nothing here is a pass until the evidence row is filled with a result from the frozen SHA. **Do not tag from this
document.** Tagging is a maintainer decision (D4 on #198).

Placeholders: `$SHA` = the frozen commit; `$PY` = a Python 3 with NumPy; `$SCRATCH` = writable scratch with enough space;
`$NVCOMP_ROOT` = nvCOMP install prefix.

## 0. Common evidence for every item

Record, once per run, in the acceptance report (`RC0_ACCEPTANCE_REPORT.md`): source SHA (`git rev-parse HEAD`, and a clean
`git status --porcelain`), binary SHA-256, exact command and exit status, hardware (CPU model, GPU model and UUID, RAM,
THP mode, driver, CUDA and nvCOMP versions), actually allocated CPUs/GPUs, input identity (SHA-256), result, and limitations.
A planned or unrun check is UNRUN, never PASS. Compilation and green CI do not establish native GPU execution, performance
or scientific correctness.

## 0b. Composition pre-conditions (track before the freeze)

The frozen SHA **F** must be a `main` commit that contains exactly the register items the maintainer accepts (#198, D4 option (a)). State of each at this revision;
update at freeze. Nothing here is verified by this document.

**Completed versus pending (this revision, main `cb3699ac`).**

| Completed pre-freeze (per item, on the stated SHAs; not re-run on the frozen SHA) | Pending QF on the frozen SHA (placeholders) |
|---|---|
| Q1 baseline qualification (`1db86902`, PR #209); raw-MRC staging M1 (#204); EER compact route E1 (#208); resident retry R1 (#207); S1 diagnosis (#212); F3/F3b fail-closed reads (#205, `f67a5866`); T3 checked arithmetic (#217, `483e881d`); C5 CPU dose symmetry **merged** (#220, `71ab841e`) with its timing measurement (#218); smaller-GPU memory admission QM (PR #225 on `483e881d`, audited by R-QM, limits in `SUPPORT.md` §8); the macOS test-harness fix (#223, `ecb7d7f7`); fixtures and format coverage (#202 `687ffc17`, #203 `5e12fecf`); the QF runbook and rehearsal (#224, `1afa03b5`); **D10 host EER memory safety** (#231, `55e30154`); **D13 report-plot undefined axis** (#230, `cb3699ac`). **Pre-freeze native check of main `cb3699ac`** ([#198 record](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6249369756)): CTest CPU 74/74, CUDA 107/107, CUDA+nvCOMP 110/110, push CI passed; **a pre-freeze result, not the frozen-SHA result** | CTest on CPU, CUDA and CUDA+nvCOMP on F; route/product campaign (§7); multi-GPU 1/2/4 (§8); the adapted compact-ingest matrix of #123; `CpuDoseSymmetry` and `CpuDoseSymmetryBase` on every released toolchain; `EerMemorySafety` and `ReportPlotUndefinedAxis` on F. **D11 (#228) is pending**: if it merges before F, `CudaStaleErrorAfterOom` is added to the required CUDA tests and the expected counts become CUDA 108 and CUDA+nvCOMP 111 (conditional; those counts belong to the QF runbook update, which needs its own independent review). The macOS statement is made; a macOS rerun on F is optional (see the macOS row) |

| Item | State at this revision | Needed before QF |
|---|---|---|
| F1: no `logfile.pdf` after a failed render | **MERGED** (#200, `ea86fc90`) | re-verify on the frozen SHA (`LogfileFromEps*` tests) |
| TST1: `CudaResidentRetryFailures` test | **MERGED** (#210, `2b3c74b3`); CUDA-only, injected failures | runs in the CUDA configurations at QF |
| F3/F3b: truncated raw MRC movie, gain reference, defect map fail closed | **MERGED** (#205, `f67a5866`): movie-level rejection, message "is truncated or unreadable"; tests `TruncatedMrcMovie`, `TruncatedGainDefect` (+ `Cuda` variants) | the two required tests pass on the frozen SHA |
| T3: checked arithmetic on the nvCOMP pre-decode path | **MERGED** (#217, `483e881d`): overflow or unreadable strip offset gives a named decline (`NotApplicable`); D1's trusted-input precondition unchanged | `DeflateLayout*` tests and the native nvCOMP controls on the frozen SHA |
| D1 (option 1), D2 (interim policy A), D5, D6, D7 | **decided**; record [`docs/rc0/decoder_trust_and_dependencies.md`](../rc0/decoder_trust_and_dependencies.md) (#199 `a1ab83f2`) | none (re-read #198 for any change) |
| D4: freeze scope and SHA | **decided: option (a)**: F is a `main` commit after the D3 merges (#223, #202, #203, #224, D10, D11 if taken, #201 final); push CI on F, then full QF on F. Scope and F themselves are not yet taken | the maintainer names F; §10 |
| **D10: EER host memory safety** ([#221](https://github.com/KingAlejandro/MotionCorr-standalone/issues/221), closed) | **fixed before freeze: MERGED** (#231, `55e30154`). A damaged container fails the movie (exit 1, no joint output); a decode that would overrun takes the retained D6 skip-and-warn path; whole-IFD truncation is still a shorter movie (E-1). Record: [`docs/rc0/eer_memory_safety/`](../rc0/eer_memory_safety/README.md) | `EerMemorySafety` on F. **The tested cases are bounded: no claim of safety on arbitrary damaged input** (`SUPPORT.md` §2) |
| **D13: report-plot undefined axis** ([#229](https://github.com/KingAlejandro/MotionCorr-standalone/issues/229), closed) | **fixed before freeze: MERGED** (#230, `cb3699ac`): `addToCPlot2D` no longer indexes `label2offset[-1]` for `EMDL_UNDEFINED`; record [`docs/rc0/report_plot_undefined_axis/`](../rc0/report_plot_undefined_axis/README.md) | `ReportPlotUndefinedAxis` on F |
| QM: memory admission on smaller GPUs | **COMPLETED pre-freeze on `483e881d`** ([PR #225](https://github.com/KingAlejandro/MotionCorr-standalone/pull/225), audited by R-QM) with documented limits (balloon on one A100 80 GB, one movie per family, free GiB at launch); `SUPPORT.md` §8 "GPU memory (QM)" carries R-QM's wording. Of the three defects in [#226](https://github.com/KingAlejandro/MotionCorr-standalone/issues/226): **D1 is required before freeze through D11 (#228, PENDING, see next row)**; **D2 (config-L admission gap) and D3 (late OOM failure) remain deferred until after RC0** | none for the completed qualification |
| **D11: stale CUDA error after a handled OOM** (#226 D1, [PR #228](https://github.com/KingAlejandro/MotionCorr-standalone/pull/228)) | **PENDING, not merged**; decided fix-before-freeze (stale error only; admission redesign D2/D3 stays out). Its D14 timing result is **1 PASS / 2 UNRESOLVED**: tutL passes (upper bound +0.07 %), tutG (+0.63 %) and e10216L (+0.70 %) exceed 0.5 % and are unresolved; the maintainer approved one confirmatory run of tutG and e10216L (4GPUs GPU3, N = 256 and 176, 16 interleaved nulls, declared in advance), and its harness is still in review. If it merges, `CudaStaleErrorAfterOom` joins the new `CUDA_REQUIRED_TESTS` list (CUDA 108, CUDA+nvCOMP 111; conditional, QF runbook update) and `SUPPORT.md` §8's stale-error sentence is revised then | merged **or** an explicit maintainer decision before F; until then the stale-error text in `SUPPORT.md` §8 is the correct statement for main |
| D14: performance rule for the D10, D11 and D13 fixes | **decided** (0.5 % upper bound on the median paired difference, plus the 2026-10-18 addenda). D10 and D13 passed on their recorded runs (some with sequential nulls, accepted by the maintainer); D11 as above | none |
| S1: CPU versus CUDA local alignment | **PROVISIONAL known limitation** (D7), prominent in README and `SUPPORT.md` §0; post-freeze priority 1 | none for RC0 |
| C5 #179 (lean port [PR #220](https://github.com/KingAlejandro/MotionCorr-standalone/pull/220)) | **MERGED** (`71ab841e`); acceptable for RC0 under a qualified-toolchain contract (`SUPPORT.md` §9, re-checked against the merged `src/cpu_dose_symmetry_mode.h` and `CMakeLists.txt`) | `CpuDoseSymmetry` and `CpuDoseSymmetryBase` run on the frozen SHA on every release toolchain |
| C6 #181, #182 | **closed, no-go** | none |
| C7 #183 / #219 | **parked**, not in RC0 | none |
| T1 #138 nvCOMP widening | **NO-GO for RC0**, parked as [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206) | none |
| L1 #141/#152 nvTIFF | **NO-GO for RC0**; not used | none |
| E2 #193 / #211 device EER renderer | **parked post-RC0** (D9) | none |
| #123 adapted compact-ingest matrix | **runs on the frozen executable at QF** (§7); result placeholder | result recorded in the evidence table (§9) |
| macOS platform statement | **MADE**: "macOS arm64: builds and runs; not qualified; known CPU CTest differences." `SyntheticRegression`: libc `rand()` differs from glibc, so the same `--seed` gives different output bytes ([#222](https://github.com/KingAlejandro/MotionCorr-standalone/issues/222)). `MultiGpuScheduling`: the test-harness `/var` symlink fix [PR #223](https://github.com/KingAlejandro/MotionCorr-standalone/pull/223) is **MERGED** (`ecb7d7f7`); see §3 for the macOS rerun | no unqualified "macOS supported" statement |
| TST2: genuine device-poisoning test | **post-RC0** ([#213](https://github.com/KingAlejandro/MotionCorr-standalone/issues/213)); current fatal-path tests inject error codes | none |
| F4 compressed-MRC decoder exit status | **documented RC0 limitation**; fix scheduled [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214); inputs must be validated independently (§7) | none |
| #215 nvCOMP file-identity check (file changing between scan and read) | post-RC0 | none |
| `RelionError` backtrace-buffer leak (`src/error.cpp:58`, found by LeakSanitizer in D10 review) | **known pre-existing post-RC0 item**, not a user-facing limitation (`SUPPORT.md` §8) | none |
| F2 known-motion launcher rewrites tracked fixtures | **documented workaround**, no code change before freeze: pass `--fixtures <scratch>` (§4) | none |
| D12: licence and notices review (#18) | **DEFERRED** (maintainer 2026-10-17: not an RC0 freeze blocker); row in §9 | none before RC0 |
| DOC1 host/VRAM memory behaviours in `SUPPORT.md` | documented | re-check line numbers at the frozen SHA |

## 1. Clean checkout

```sh
git clone https://github.com/KingAlejandro/MotionCorr-standalone.git mc-rc0 && cd mc-rc0
git checkout "$SHA" && git rev-parse HEAD && git status --porcelain      # must print the SHA and nothing else
python3 -m venv "$SCRATCH/mc-venv" && "$SCRATCH/mc-venv/bin/pip" install numpy
PY="$SCRATCH/mc-venv/bin/python"
```

Why a venv: with `BUILD_TESTING=ON` the CMake configure fails unless the chosen Python imports NumPy
(`CMakeLists.txt:422-428`: "BUILD_TESTING=ON requires Python 3 with 'numpy' installed."). `README.md` now states this next to
the build prerequisites. **LOCAL-OK**: reproduced here (system Python 3.14 has no NumPy); configure succeeds with
`-DPython3_EXECUTABLE=<venv python>`.

Dependencies: README "Prerequisites" (CMake >= 3.21, FFTW double and float, OpenMP, libtiff, libpng, libjpeg, zlib,
Ghostscript for the PDF).

## 2. Builds

### 2a. CPU

```sh
cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$PY"
cmake --build build-cpu --parallel 8
./build-cpu/motioncorr --version
./build-cpu/motioncorr --use_own --help
shasum -a 256 build-cpu/motioncorr          # sha256sum on Linux
```

**LOCAL-OK** (macOS arm64, AppleClang 21, FFTW 3.3.11, libtiff 4.7.2; first run at main `1db86902`, repeated at the merge head `67b5315b`
= `2b3c74b3` + this branch's docs): configure and build exit 0 (about 22 s wall with `--parallel 6`). `--version` prints
`RELION version: 5.1.0-motioncorr-standalone` and `Precision: BASE=double`, exit 0. `--use_own --help` prints 58 lines of
options, exit 0. **Plain `--help` exits 1** with "You have to choose either UCSF MotionCor2 or RELION's own implementation"
because the program parses `--use_own` before it prints usage; the support page and the README must give the
`--use_own --help` form. Binary SHA-256 on this machine: `6d9ee043e004734fdec39590f2e6c3edc5fe51b1d7139ecfd3716c44ddde4bc2` at `1db86902`,
`c8755d48e58fd783d4730efb66dd30541f39f25714eb87afbe5ef96331d31847` at `67b5315b` (local builds; not release artefacts).

### 2b. CUDA without nvCOMP — UNRUN

```sh
cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
      -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$PY"
cmake --build build-cuda --parallel 8
./build-cuda/motioncorr --version
```

Read back the configure line `motioncorr_core CUDA architectures: ...` (`CMakeLists.txt:177`). The default is 80 only when the
variable and `CUDAARCHS` are both unset (`CMakeLists.txt:168-169`); an sm80 binary is not evidence for other devices. Add a
compiled-cubin check (for example `cuobjdump --list-elf build-cuda/motioncorr`) and record its output.

### 2c. CUDA with nvCOMP — UNRUN

```sh
cmake -S . -B build-nvcomp -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVCOMP_ROOT" \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$PY"
cmake --build build-nvcomp --parallel 8
```

`USE_NVCOMP=ON` without the headers and library is a configure error (`CMakeLists.txt:202`). Record the nvCOMP version
(the #186 and #194 evidence used 5.3 with CUDA 12.8). The release notes must carry the decided input-trust precondition
(D1 option 1: complete, unmodified files; `--ingest compact` for files of unknown integrity) and the optional-SDK policy (D2 interim policy A: optional,
default OFF, not vendored, no project-distributed linked binaries) from `SUPPORT.md` §7 and the record [`docs/rc0/decoder_trust_and_dependencies.md`](../rc0/decoder_trust_and_dependencies.md); T3 checked arithmetic is merged (#217) and does not change the D1 precondition.

## 3. CTest

```sh
ctest --test-dir build-cpu --output-on-failure
"$PY" tools/validate_test_collection.py --test-dir build-cpu
```

Use the same two commands for `build-cuda` and `build-nvcomp` (UNRUN). Record the **collected count and the executed
inventory** from that configuration; do not predict a count, and do not count a test that was not registered as an executed
pass. Most `Cuda*` tests are registered only in CUDA builds (`CMakeLists.txt:647` onward); `CudaValidationParser` is
device-free and is registered in CPU builds too (`CMakeLists.txt:611-614`; it ran in the local CPU suite). Several need a GPU
(label `hardware`, for example `CudaPreprocessingFailurePaths`, `CMakeLists.txt:897-902`). `CudaAdler32`,
`CudaNvcompAcceptanceFailures` and `CudaNvcompReconstructionFailures` exist only with `-DUSE_NVCOMP=ON`
(`CMakeLists.txt:918` onward). **`CudaU16FailurePaths` is registered only if you configure with
`-DMOTIONCORR_U16_TEST_MOVIE=<uint16 TIFF>`** (and `-DMOTIONCORR_U16_TEST_STAGE_BYTES=<bytes in one uint16 frame>`, default
28477960); without it the test is absent, not passed (`CMakeLists.txt:973-992`).

**LOCAL-OK, with one failure (CPU build, macOS), revision-7 run at the merge head `49efcd43` (main `cb3699ac` + this branch's docs; `git diff cb3699ac HEAD -- . ':!docs' ':!README.md'` is empty): 74 collected, 72 passed, 1 failed (`SyntheticRegression`), 1 skipped (`NativeMovieStaging`); `validate_test_collection.py` rc 0 with 74 collected; the CPU binary is `666a3d51...9518d`.** AppleClang 21.0.0, FFTW 3.3.11, libtiff 4.7.2, NumPy 2.5.4 in a venv, `--parallel 8`, CTest `-j 2` (146.5 s). `pbzip2` is not installed here, so the compressed-MRC cases of `InputFormats` that need it are **waived as UNRUN by the CMake configure step** (a waiver, not a pass); `zstd` and `xz` are present. The configure step reports the original dose-weighting loop on this toolchain (AppleClang arm64; AUTO enables the symmetric path only on x86-64 GCC without FMA), and `CpuDoseSymmetry` and `CpuDoseSymmetryBase` both pass on it. `EerMemorySafety`, `ReportPlotUndefinedAxis`, `InputFormats` and `CutDownMovie` pass on macOS. **`MultiGpuScheduling` now passes** (it failed at revision 6; #223 is merged). Earlier macOS runs: at `861afa5d` (main `483e881d`) 68 collected, 65 passed, 2 failed (`SyntheticRegression`, `MultiGpuScheduling`), 1 skipped; at `67b5315b` 60 collected, 57 passed, 2 failed, 1 skipped; at `1db86902` the same two failed (59 collected, 56 passed, 1 skipped). The Linux CPU qualification at `1db86902` (W-QUAL, [PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209))
collected 59/89/92 tests (CPU, CUDA, CUDA+nvCOMP) and passed 58/89/92 with 0 skipped; its one CPU failure, `ProfilingKit`, was a 30 s
subprocess timeout under host load about 27 and passed on rerun. The **pre-freeze Linux check of main `cb3699ac`** reported 74/74 (CPU), 107/107 (CUDA) and 110/110 (CUDA+nvCOMP) with push CI passing ([#198 record](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6249369756)); it is not a frozen-SHA result and is not re-run here.

**Tests required at QF that were added after `1db86902`:** `TruncatedMrcMovie` and `TruncatedGainDefect` (F3/F3b, #205; CUDA builds also register `TruncatedMrcMovieCuda` and `TruncatedGainDefectCuda`), the six
`DeflateLayoutMutant_*` controls (T3, #217; they must **fail** by design, `WILL_FAIL`), `LogfileFromEpsMutant_concat_cleanup` (F1), **`CpuDoseSymmetry` and `CpuDoseSymmetryBase`** (C5, #220; both are in `tools/validate_test_collection.py`; `CpuDoseSymmetry` must pass on every toolchain released with the symmetric path enabled, `SUPPORT.md` §9),
**`InputFormats` and `CutDownMovie`** (#202, #203; format coverage; the opt-in `RealCutdown` test is registered only when `-DMC_REAL_CUTDOWN_DIR=<assets>` is given, `CMakeLists.txt:504`, and a test that was not registered is not a pass), **`EerMemorySafety`** (D10, #231) and **`ReportPlotUndefinedAxis`** (D13, #230). All are in the required list of `tools/validate_test_collection.py` on main.
**Conditional on D11 (#228, pending):** if it merges, `CudaStaleErrorAfterOom` joins the required CUDA tests (new `CUDA_REQUIRED_TESTS` list), and the expected counts become CPU 74, CUDA 108 and CUDA+nvCOMP 111. Those counts are **not** established here; they belong to the QF runbook update, which needs its own independent review. Record the actual counts at QF and do not predict them.

**`ProfilingKit` is load sensitive.** `tools/profiling/tests/test_import_subset_boundaries.py` has a hard 30 s subprocess timeout. Run
CTest on a quiet host, or record a timeout and its rerun explicitly. (Locally it passed in 64.7 s of CTest wall time.)

| Test | Result on macOS (revision-7 run) | Status |
|---|---|---|
| `SyntheticRegression` | FAIL (same failure in the revision-7 run: max pixel difference 2.364986e+01, RMSE 3.119288e-01). Full-precision figures from an earlier run: image pixel diff 23.649856567382812 (max), RMSE 0.311928825603332, shift RMSD 0.003305323357857738 px; asserts exact 0.0 | **cause: libc `rand()` differs from glibc**, so hot-pixel replacement (about 391 replaced pixels) and the output bytes differ for the same `--seed` ([#222](https://github.com/KingAlejandro/MotionCorr-standalone/issues/222), W-MAC); it has failed on macOS since the test was created. Documented only; a glibc-compatible `rand` scratch build reduced the difference to 1.07. Tier A on the committed fixture passes, see §5 |
| `MultiGpuScheduling` | **PASS** at the revision-7 run (59.3 s). At revision 6 it failed at `tests/test_tomography_endpoint.py:122`: "validator rejects the healthy published tree" (73 of 74 checks passed; reproduced when run alone) | **cause was the test-harness `/var` symlink issue** (macOS temporary paths), fixed by [PR #223](https://github.com/KingAlejandro/MotionCorr-standalone/pull/223) (**MERGED**, `ecb7d7f7`); it also passes on Linux (#209, and in the pre-freeze check of `cb3699ac`) |
| `NativeMovieStaging` | SKIPPED (Linux-only) | skip is not a pass |

**macOS platform statement: "macOS arm64: builds and runs; not qualified; known CPU CTest differences."** The one remaining macOS failure, `SyntheticRegression`, is explained (above) and is not waived; no unqualified "macOS supported" statement is made.
None of these may be relaxed or waived to pass RC0. On Linux, `SyntheticRegression` and `MultiGpuScheduling` are expected to pass and `NativeMovieStaging` to run (main CI is green per #198);
QF must show it. A failure there is a release blocker, not an inherited macOS note. A macOS rerun on F is optional and, if made, is a separate row; it does not qualify macOS.

## 4. Known-motion launcher (Tier C)

```sh
"$PY" tools/run_known_motion_gates.py --binary build-cpu/motioncorr --outdir "$SCRATCH/km" \
    --fixtures "$SCRATCH/km-fixtures" --json "$SCRATCH/km.json"
git status --porcelain                           # must still print nothing
# CUDA row (UNRUN): same command with  --gpu 0  and build-cuda/motioncorr
```

**LOCAL-OK** (CPU, macOS): exit 0, OVERALL PASS in 5.3 s wall. Gate cases `km_global_hisnr`, `km_local_hisnr` and
`km_local_nonsquare` PASS (9/9 gated metrics in the case printed last); `km_local_noisy` is role `characterization` and
**FAIL**s visibly without blocking (`docs/gate_contract.md` §1, Tier C; the launcher says characterization failures stay
visible). Field difference `--j 1` versus `--j 4` is 0 px (identical).

**Always pass `--fixtures <scratch dir>`.** The launcher's `--fixtures` default is the tracked `test-data/known_motion` and
`--regenerate` is on by default (`tools/run_known_motion_gates.py:244-266`); the generator stamps the current HEAD into
`source_commit` and replaces the ground-truth JSON files (`test-data/generate_known_motion_fixture.py`, also `MANIFEST.json`
provenance). Without the flag the first local run rewrote `source_commit` in the four tracked
`test-data/known_motion/*_ground_truth.json` files (movie hashes unchanged) and left four ignored `.mrcs` files. The tool is
not changed for RC0 (register F2). **LOCAL-OK, re-run with the flag** (CPU, macOS, main `1db86902`): exit 0, OVERALL PASS, same four
case verdicts, `git status --short` empty, fixtures generated under the scratch directory.

## 5. Tier A regression on the committed fixture

```sh
PYTHON="$PY" ./tools/run_regression_tests.sh "$PWD/build-cpu/motioncorr"
```

Give an **absolute** binary path: the script changes directory before it runs the binary, so `./build/motioncorr` fails with
"No such file or directory" (reproduced here). **LOCAL-OK**: exact gate PASS, pixel-identical, 0 STAR differences, 0 header
difference bytes, complete coverage; ground-truth recovery reported at 0.071437 px RMS, 0.100020 px max (reported, not gated;
`docs/gate_contract.md` §6).

## 6. Example run and expected inventory

```sh
( cd test-data/fixtures && ../../build-cpu/motioncorr --i synthetic_128x128_8frames.star \
      --o "$SCRATCH/ex1" --use_own --j 2 --ingest_witness "$SCRATCH/ex1.witness" )
```

The subshell keeps the working directory at the checkout root for the commands that follow.

**LOCAL-OK**: exit 0. Witness file: `synthetic_128x128_8frames.mrcs float`. Output inventory (no `gs` installed on the validation
machine): `batch.pdf`, `batch.pdf.lst`, `corrected_micrographs.star`, `corrected_micrographs_all_rlnAccumMotion{Early,Late,Total}.eps`,
`header.pdf`, `header.pdf.lst`, `synthetic_128x128_8frames.{log,mrc,star}`, `synthetic_128x128_8frames_shifts.eps`. **`logfile.pdf` was
not written** and `batch.pdf` and `header.pdf` are zero-byte placeholders, because `gs` was missing; the program printed the gs error and exited 0 (`src/CPlot2D.cpp:66-98`). With `gs`
the inventory is **UNRUN**; record the real list at QF. A run with `--dose_weighting --save_noDW` adds `_noDW.mrc`
(`--save_noDW` without dose weighting writes no separate file: the unweighted sum is the main `.mrc`,
`src/motioncorr_runner.cpp:4068-4074`), and `--even_odd_split` adds `_EVN.mrc` and `_ODD.mrc`.

Refusal checks on the CPU build (**LOCAL-OK**, each exits 1): `--gpu 0` (line 403, "built without CUDA support"),
`--gpu 0:1` (line 368, device list rejected), `--ingest compact` and `--ingest nvcomp` (line 246), `--ingest bogus` (line 164).

## 7. Real-format product campaign (UNRUN)

There is no single script for this. Reuse the existing pieces and declare unrun rows instead of widening the campaign:

- Corpus and hashes: `docs/workload_corpus/corpus.md`, `families.json`, `docs/workload_corpus/tools/fetch_corpus.py`, `docs/workload_corpus/tools/setup_corpus.py`
  (SHA-256 verified; 22 of 22 held-family files in the #186 pass).
- **Two comparison tools for two questions. Do not mix them.**
  1. **Cross-backend (CPU versus CUDA): `tools/compare_motioncorr.py --gate backend`, one movie at a time**, plus structural
     validation of each tree. The backend profile keeps the relaxed absolute image RMSE (0.020), maximum pixel error (5), global
     shift limits (0.02 / 0.05 px) and static STAR checks, requires complete image and movie-STAR coverage, and requires a
     `--test-log` with a parseable elapsed time, peak RSS and successful exit status; the 0.001 relative-RMSE figure is reported
     as a **non-blocking diagnostic** (`docs/gate_contract.md` "Explicit backend profile"; `tools/compare_motioncorr.py:481-496,
     749-772`). It does not accept threshold overrides and must not be described as passing the relaxed gate. The log is a GNU
     `/usr/bin/time -v` log, so this row runs on Linux. **UNRUN** (needs a CUDA arm). Do not use strict tree identity here:
     CUDA output is not byte-identical to CPU output.
  2. **Same-backend invariance: `docs/issue85_laneC/compare_output_trees.py` with a manifest** for implementation, ingest-route,
     repeat and worker-count comparisons (for example `--ingest compact` versus `float` on one backend, one GPU versus four
     workers, a repeat run). It validates each arm against the manifest and then compares MRC header, extended header and pixel
     payload hashes **exactly**, STAR content and logs, normalising only the output root, duration lines and the MRC label date
     (`docs/issue85_laneC/compare_output_trees.py:467-478`; `--products-only` still compares pixels exactly). **LOCAL-OK** on two CPU runs of the
     128 x 128 fixture (a manifest with `movies: ["Movies/..."]` and `expected_shape_xyz: [128,128,1]`): "Validated 1 movies, 1 MRC
     images, 2 STAR files, 16384 pixels per arm; Comparison: products; status=PASS; different files=0". Needs NumPy; movie names
     must carry the `Movies/` prefix the manifest expects.
- **Input integrity before every row (D1, D5, D6, D10).** Compressed MRC: run `xz -t`, `zstd -t` or `bzip2 -t`/`pbzip2 -t` on every input first
  (F4, fix scheduled #214). nvCOMP rows: use complete, unmodified acquisition files (D1 option 1); use `--ingest compact` for files of unknown integrity
  or still being written. EER rows: pass `--expected_frames` or per-movie STAR frame counts. Raw MRC truncation is rejected (F3/F3b, #205 merged); compressed MRC is not (F4). A damaged EER container fails the movie and a fraction that would overrun is skipped with the D6 warning (D10, #231 merged; `SUPPORT.md` §2): the real-format rows use valid files, and D10 is a bounded result, so no row may treat a damaged EER file as supported input.
- **Route-log allowance for signed MRC.** Declared route-record log prefixes for `compare_output_trees.py --allow-added-log-line` must include
  `Released native int` for signed raw MRC (#195 added `Released native int16/int8 host staging after device forward FFT.`); the #209 campaign
  declared four prefixes in advance (`nvCOMP ingestion`, `Staging this movie as native`, `Released native uint` and one more), and its signed-MRC cases
  (10164, 10216) still showed that extra line, so the allowance needs `Released native int` (#209 README, "PASS*").
  The comparator cannot compare `_noDW`/`_EVN`/`_ODD` products or mixed-shape trees (#209 tooling note); compare those with
  `tools/profiling/lib/identity.py` (`mcprof`) or per product.
- Per-row route proof: `--ingest_witness` plus a pinned `--ingest` where the row is meant to take one route. The witness is a
  route-selection record, not a completion record (`SUPPORT.md` §2); pair it with the product check.

Cross-backend per-movie command (UNRUN; GNU time is required for `--test-log`):

```sh
/usr/bin/time -v ./build-cuda/motioncorr --i movies.star --o "$OUT/cuda" --use_own --gpu 0 --j 8 <row options> 2> "$OUT/cuda.time"
"$PY" tools/compare_motioncorr.py --gate backend --require-complete-coverage \
    --ref-mrc "$OUT/cpu/Movies/<movie>.mrc"  --test-mrc "$OUT/cuda/Movies/<movie>.mrc" \
    --ref-star "$OUT/cpu/Movies/<movie>.star" --test-star "$OUT/cuda/Movies/<movie>.star" \
    --test-log "$OUT/cuda.time" --json-out "$OUT/<movie>.backend.json"
```

The `--help` of this tool accepts these flags (**LOCAL-OK**). Dataset verdicts are conjunctive over movies. Run every movie.

Same-backend row template (run each row once per ingest route or worker layout of the same backend):

```sh
./build-cuda/motioncorr --i movies.star --o "$OUT/<row>" --use_own --gpu 0 --j 8 \
    --ingest <auto|nvcomp|compact|float> --ingest_witness "$OUT/<row>.witness" <row options>
"$PY" docs/issue85_laneC/compare_output_trees.py --manifest <row manifest> --input-star movies.star \
    "$OUT/<same-backend baseline>" "$OUT/<row>"
```

The CPU arm of a row is the reference for the cross-backend check only; it is not a strict-identity baseline for the CUDA arm.

| Row | Input | Route to prove (witness) | Options | Corpus family |
|---|---|---|---|---|
| R1 | TIFF 16-bit Deflate | `nvcomp` on the nvCOMP build; `compact` otherwise | gain, dose weighting, 5 x 5 patches | tutorial |
| R2 | TIFF 8-bit LZW BigTIFF | `compact` | gain or none, dose weighting | e10361, e10641, e10441 |
| R3 | MRC float32 | `float` | dose weighting | e10028 |
| R4 | MRC mode 0 (int8) and mode 1 (int16) | `compact` | dose weighting | e10164, e10216 |
| R5 | EER, grouping and upsampling 1 (4096 x 4096, encoding 65001 in the corpus) | `compact` | `--eer_grouping`, gain, **`--expected_frames`** (D6: otherwise a truncated EER processes as a shorter movie) | e10474f3/f4, e12963 |
| R6 | EER with `eer_grouping` x (4 at upsampling -1, else 1) above 65535 | `float`, log line present | needs a movie with at least 3 x grouping fractions, so likely unreachable with real EER; if not run, declare UNRUN and cite the #196 overflow-guard control | synthetic |
| R7 | compressed MRC (`.mrc.zst`, `.mrc.xz`, `.mrc.bz2`) | `float` | needs the external decompressor; **validate the file first** with `xz -t`, `zstd -t` or `bzip2 -t`/`pbzip2 -t` (F4: the decoder exit status is not checked, `SUPPORT.md` §6); PR #204 tested `.bz2` through a `bzip2 -cd` shim because `pbzip2` was absent | one small file |
| R8 | pinned-route refusals | movie fails, no completion STAR; a refusal writes no witness line, so prove the intended route with a positive control on an eligible movie | `--ingest nvcomp` / `compact` on an ineligible movie | any ineligible movie |
| R9 | options | each option arm completes with complete products and passes its **named invariant**; option-on versus option-off products are **not** expected to be equal where the option changes them. Invariants: `--save_noDW` adds `_noDW.mrc` and leaves the dose-weighted `.mrc` equal to the run without it (same backend); `--even_odd_split` adds `_EVN`/`_ODD` and leaves the main `.mrc` equal; binning, `--group_frames`, first/last frame, defect file and gain rot/flip change the products by design, so check complete products, geometry and sampling, and the cross-backend backend gate against the CPU arm of the **same** options | `--save_noDW` (with `--dose_weighting`), `--even_odd_split`, `--bin_factor` (even binned dimensions), `--group_frames`, first/last frame, defect file, gain rot/flip | tutorial |
| R10 | direct input and glob | complete products | `--i 'Movies/*.tiff' --angpix --voltage` | tutorial subset |
| R11 | unchanged-setting resume | no reprocessing, identical tree | `--only_do_unfinished` | tutorial subset |
| R13 | truncated raw MRC movie, gain reference, defect map (F3/F3b, merged) | movie-level rejection: exit 1, "is truncated or unreadable", no completion STAR, no joint output; a truncated gain or defect map fails every movie and the job; valid input byte-identical to the unfaulted run | truncated copies of one movie, one gain, one defect map | any small raw MRC family |
| R14 | **#123 adapted compact-ingest support matrix (placeholder)** | to be run on the frozen executable at QF; result **pending RC0 QF** | per #123 | per #123 |
| R12 | one checked failure | named failure, no completion STAR for that movie, healthy movies' per-movie products retained, **no joint output for the batch**; partial or earlier per-movie files for the failed movie may exist (`SUPPORT.md` §6): record what is on disk, do not assert absence | truncated movie | one damaged copy |

The #186 families and options are the starting point; their dose-per-frame and voltage values are placeholders for several
families, and corpus gain orientation is the default (`docs/workload_corpus/corpus.md`). Those runs timed the work; QF must
compare products. R6 and R7 are not in the corpus and need small purpose-built inputs.

**Resume (R11 and the #149 limit).** Same-settings no-op resume is the supported case. **LOCAL-OK** on the fixture: a rerun
with `--only_do_unfinished` left the MRC untouched; adding `--dose_weighting --dose_per_frame 1.5` to the same `--o` also left
it untouched (same modification time), i.e. changed settings are **not** detected. Record this as a limitation, not a
pass of "resume under changed settings".

## 8. Multi-GPU dataset run (UNRUN)

```sh
"$PY" tools/multi_gpu/run_dataset.py \
  --binary "$PWD/build-cuda/motioncorr" --star "$STAR" --out "$OUT/w4" \
  --launcher-args="--devices $UUID0,$UUID1,$UUID2,$UUID3 --cpus $CPUS0;$CPUS1;$CPUS2;$CPUS3 --cpu-budget $BUDGET" \
  --required-products='.mrc,.star,_shifts.eps' -- \
  --use_own --j 8 --max_io_threads 8 --ingest auto --dose_weighting --dose_per_frame "$DOSE" \
  --angpix "$ANGPIX" --voltage "$KV" --gainref "$GAIN"
```

Adapted from `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`. Select devices by UUID from `nvidia-smi -L`, with disjoint CPU masks
taken from the actual allocation. The output directory must not exist. Required: `dataset_status.json` with `dataset_ready: true`
and `verdict: PASS`; every worker's device witness on its intended, distinct GPU; the complete product tree compared with a
single-process single-GPU run of the same input on the **same backend** (`compare_output_trees.py`, strict; this is a
worker-count invariance check, not a CPU comparison); **Ghostscript installed** (the aggregate renders
`logfile.pdf` strictly). Repeat at 1, 2 and 4 devices.

**Verified on Linux at `1db86902`** (W-QUAL, PR #209): 1, 2 and 4 workers on the 24 tutorial movies, configs G and L, dataset-endpoint PASS
6/6, distinct witnessed UUIDs, identical products across worker counts and to a single process, real-Ghostscript `logfile.pdf` (30 pages).
Re-verification on the frozen SHA is the QF row.

**LOCAL-OK, partial:** `run_dataset.py` with `--launcher-args="--workers 2 --no-witness"` on two CPU workers (the two 128 x 128
fixtures): both workers exited 0 and 8 files were staged, then the aggregate step failed with "Aggregate PDF generation failed"
because `gs` is not installed; `run_dataset.py` exited 3, `dataset_ready: false`, `verdict: FAIL`. The success path on macOS is
**UNRUN**. Python 3.14 prints `SyntaxWarning: 'return' in a 'finally' block` for `run_dataset.py:172`.

Also required before RC0 (from `docs/multi_gpu/CURRENT_MAIN_ACCEPTANCE.md`): an injected owned-worker failure with a
TERM-ignoring descendant, a late writer fault and a report failure; each must name the failure, not report dataset-ready, and
leave no owned process.

## 9. Evidence table to complete at QF

| Item | Command section | Source SHA | Binary SHA-256 | Hardware | Result | Verdict |
|---|---|---|---|---|---|---|
| CPU build + ctest + collection | 2a, 3 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| CUDA build + ctest + cubin read-back | 2b, 3 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| CUDA + nvCOMP build + ctest | 2c, 3 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Tier A | 5 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Known-motion launcher, CPU and CUDA | 4 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Example run and inventory, with `gs` | 6 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Real-format rows R1-R12 | 7 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Multi-GPU 1/2/4 dataset run, failure injection | 8 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| #123 adapted compact-ingest matrix (R14) | 7 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| `CpuDoseSymmetry` and `CpuDoseSymmetryBase` on each released toolchain (#220 merged) | 3 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| `EerMemorySafety` (D10), `ReportPlotUndefinedAxis` (D13), `InputFormats`, `CutDownMovie` required tests | 3 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| D11 (#228, stale CUDA error after OOM) and `CudaStaleErrorAfterOom` | 3 | **PENDING, not merged** | n/a | n/a | D14 timing 1 PASS / 2 UNRESOLVED; confirmatory run approved, harness in review | pending merge; counts CUDA 108 / nvCOMP 111 only if it merges |
| F3/F3b required tests (`TruncatedMrcMovie`, `TruncatedGainDefect`) and T3 `DeflateLayout*` | 3, 7 | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Smaller-GPU memory admission (QM) | n/a | `483e881d` (PR #225) | `d8e7a003...f98173` (build-nvcomp `motioncorr`) | one A100 80 GB, VRAM balloon | 162 runs, no crash, hang or wrong output; limits in `SUPPORT.md` §8 | completed pre-freeze, documented limits |
| macOS platform statement (W-MAC) | 3 | statement made | n/a | n/a | not qualified; known CPU CTest differences; #223 merged (`ecb7d7f7`), macOS rerun in §3 | made; not qualified |
| EER damaged-input handling (D10, #221) | n/a | merged `55e30154` (#231) | n/a | 4GPUs (D10 record) | fixed before freeze; 37 fixtures controlled with 0 sanitizer reports; 24/24 valid-input products byte-identical; **bounded cases, not an arbitrary-damaged-input claim**; whole-IFD truncation and D6 skip-and-warn unchanged | merged; frozen-SHA rerun pending RC0 QF |
| Report-plot undefined axis (D13, #229) | n/a | merged `cb3699ac` (#230) | n/a | cpu64 / 4GPUs (D13 record) | fixed before freeze; D14 CPU timing passed | merged; frozen-SHA rerun pending RC0 QF |
| Licence and notices review (#18: six ambiguous notices in `CPlot2D.cpp/.h` and four `src/acc/hip` headers) | maintainer | n/a | n/a | n/a | **deferred** (D12, maintainer 2026-10-17: not an RC0 freeze blocker) | deferred |
| Pre-freeze native check of main `cb3699ac` (**cited, not frozen-SHA evidence**) | 3 | `cb3699ac` | CPU `f1ff7fa4…`, CUDA `a9117cc2…`, CUDA+nvCOMP `9f721c36…` | 4GPUs, GPU0 and GPU1 pinned by UUID, NUMA node 0 | CTest 74/74, 107/107, 110/110; collection checks rc 0; push CI run 39122394239 passed ([#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6249369756)) | reported pre-freeze; the QF rows above stay pending |

## 10. Tag procedure (do not execute from this draft)

Identities, kept separate (D4, option (a)):

- **F**, the frozen **source** SHA: a `main` commit after the D3 merges. Push CI and the full QF run on F. `git rev-parse HEAD` in the QF checkout must print F, and the tree must be clean.
- **Evidence commits** (docs-only), made after F: the filled acceptance report and evidence table, and nothing else. They may touch only `docs/rc0` and `docs/release`.
- **The tag target** is named by the maintainer explicitly. It is F or a later evidence commit; it is never chosen by this document or inferred.

1. Maintainer declares scope and F (D4). The register items are closed and push CI is green on F.
2. QF evidence table complete on F, every row PASS or explicitly UNRUN/declared unsupported; the acceptance report filled and linked.
3. **Source-identity check, with F and the candidate tag target T:** `git diff F T -- . ':!docs/rc0' ':!docs/release'` must print nothing. A non-empty diff means the evidence did not come from the tagged source; stop and report. Record F, T and the empty diff in the report.
   Every binary hash and result in the evidence table must name F, not T.
4. Maintainer creates an annotated tag on T, for example `git tag -a vX.Y.Z-rc0 <T> -m "RC0"`, and pushes it. Release notes
   link `SUPPORT.md`, the acceptance report, known limitations and D1/D2 outcomes, and state F (the tested source) and T (the tagged commit).
5. After the tag, only the bug-fix policy in `POST_FREEZE_TEST_PLAN.md` applies.

Because `README.md` sits outside `docs/rc0` and `docs/release`, it must be final in F; a README change after F fails the check in step 3.

No tag, release, merge or push to `main` is made by this document or its author.
