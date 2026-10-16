# RC0 release checklist (DRAFT)

Status: **draft, pre-freeze.** Commands below were written against main `1db86902`. Each command is tagged:

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

## 1. Clean checkout

```sh
git clone https://github.com/KingAlejandro/MotionCorr-standalone.git mc-rc0 && cd mc-rc0
git checkout "$SHA" && git rev-parse HEAD && git status --porcelain      # must print the SHA and nothing else
python3 -m venv "$SCRATCH/mc-venv" && "$SCRATCH/mc-venv/bin/pip" install numpy
PY="$SCRATCH/mc-venv/bin/python"
```

Why a venv: with `BUILD_TESTING=ON` the CMake configure fails unless the chosen Python imports NumPy
(`CMakeLists.txt:298-304`: "BUILD_TESTING=ON requires Python 3 with 'numpy' installed."). The README's build command does not
mention this. **LOCAL-OK**: reproduced here (system Python 3.14 has no NumPy); configure succeeds with
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

**LOCAL-OK** (macOS arm64, AppleClang 21, FFTW 3.3.11, libtiff 4.7.2, Python 3.14.8; main `1db86902`): configure and build exit 0
(about 22 s wall with `--parallel 6`, 57 compiler warnings, none treated as errors). `--version` prints
`RELION version: 5.1.0-motioncorr-standalone` and `Precision: BASE=double`, exit 0. `--use_own --help` prints 58 lines of
options, exit 0. **Plain `--help` exits 1** with "You have to choose either UCSF MotionCor2 or RELION's own implementation"
because the program parses `--use_own` before it prints usage; the support page and the README must give the
`--use_own --help` form. Binary SHA-256 on this machine: `6d9ee043e004734fdec39590f2e6c3edc5fe51b1d7139ecfd3716c44ddde4bc2`
(a local build; not a release artefact).

### 2b. CUDA without nvCOMP — UNRUN

```sh
cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
      -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$PY"
cmake --build build-cuda --parallel 8
./build-cuda/motioncorr --version
```

Read back the configure line `motioncorr_core CUDA architectures: ...` (`CMakeLists.txt:127`). The default is 80 only when the
variable and `CUDAARCHS` are both unset (`CMakeLists.txt:118-119`); an sm80 binary is not evidence for other devices. Add a
compiled-cubin check (for example `cuobjdump --list-elf build-cuda/motioncorr`) and record its output.

### 2c. CUDA with nvCOMP — UNRUN

```sh
cmake -S . -B build-nvcomp -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVCOMP_ROOT" \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$PY"
cmake --build build-nvcomp --parallel 8
```

`USE_NVCOMP=ON` without the headers and library is a configure error (`CMakeLists.txt:152`). Record the nvCOMP version
(the #186 and #194 evidence used 5.3 with CUDA 12.8). The decoder trust boundary (D1) and licence (D2) are open on #198; the
release notes must carry whatever the maintainer decides.

## 3. CTest

```sh
ctest --test-dir build-cpu --output-on-failure
"$PY" tools/validate_test_collection.py --test-dir build-cpu
```

Use the same two commands for `build-cuda` and `build-nvcomp` (UNRUN). Record the **collected count and the executed
inventory** from that configuration; do not predict a count. The `Cuda*` tests are registered only in CUDA builds
(`CMakeLists.txt:468` onward) and some need a GPU and an nvCOMP build (`CudaPreprocessingFailurePaths`,
`CMakeLists.txt:705-709`).

**LOCAL-OK, with failures (CPU build, main `1db86902`):** 59 collected, 56 passed, **2 failed, 1 skipped**.
`validate_test_collection.py` reports PASS with 59 collected tests.

| Test | Result on macOS | Status |
|---|---|---|
| `SyntheticRegression` | FAIL: image pixel diff 23.649856567382812 (max), RMSE 0.311928825603332, shift RMSD 0.003305323357857738 px; asserts exact 0.0 | inherited: same numbers in the #178 current-main evidence (`docs/cpu_stream_20261014/current-main-20261016/README.md`); the committed reference is a Linux output. Tier A on the committed fixture passes, see §5 |
| `MultiGpuScheduling` | FAIL at `tests/test_tomography_endpoint.py:122`: "validator rejects the healthy published tree"; 73 of 74 checks pass; reproduces when run alone | inherited: same evidence file ("the device-free scheduling validator rejects its healthy tree in both"). Cause not diagnosed here |
| `NativeMovieStaging` | SKIPPED (Linux-only) | skip is not a pass |

None of these may be relaxed or waived to pass RC0. On Linux, `SyntheticRegression` and `MultiGpuScheduling` are expected to pass and `NativeMovieStaging` to run (main CI is green per #198);
QF must show it. A failure there is a release blocker, not an inherited macOS note.

## 4. Known-motion launcher (Tier C)

```sh
"$PY" tools/run_known_motion_gates.py --binary build-cpu/motioncorr --outdir "$SCRATCH/km" --json "$SCRATCH/km.json"
# CUDA row (UNRUN): add  --gpu 0  and use build-cuda/motioncorr
git checkout -- test-data/known_motion          # see note
```

**LOCAL-OK** (CPU, macOS): exit 0, OVERALL PASS in 5.3 s wall. Gate cases `km_global_hisnr`, `km_local_hisnr` and
`km_local_nonsquare` PASS (9/9 gated metrics in the case printed last); `km_local_noisy` is role `characterization` and
**FAIL**s visibly without blocking (`docs/gate_contract.md` §1, Tier C; the launcher says characterization failures stay
visible). Field difference `--j 1` versus `--j 4` is 0 px (identical).

Note: the launcher regenerates the fixtures in place. It rewrote `source_commit` in the four tracked
`test-data/known_motion/*_ground_truth.json` files and created four ignored `.mrcs` files. Movie hashes were unchanged. Run it from
a scratch clone, or restore the tracked files afterwards, so `git status --porcelain` stays clean for the next step.

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
cd test-data/fixtures
../../build-cpu/motioncorr --i synthetic_128x128_8frames.star --o "$SCRATCH/ex1" --use_own --j 2 \
    --ingest_witness "$SCRATCH/ex1.witness"
```

**LOCAL-OK**: exit 0. Witness file: `synthetic_128x128_8frames.mrcs float`. Output inventory (no `gs` installed on the validation
machine): `batch.pdf`, `batch.pdf.lst`, `corrected_micrographs.star`, `corrected_micrographs_all_rlnAccumMotion{Early,Late,Total}.eps`,
`header.pdf`, `header.pdf.lst`, `synthetic_128x128_8frames.{log,mrc,star}`, `synthetic_128x128_8frames_shifts.eps`. **`logfile.pdf` was
not written** because `gs` was missing; the program printed the gs error and exited 0 (`src/CPlot2D.cpp:66-87`). With `gs`
the inventory is **UNRUN**; record the real list at QF. The same inventory command for a `--save_noDW` / `--even_odd_split`
run adds `_noDW.mrc` and `_EVN.mrc`/`_ODD.mrc` (`src/motioncorr_runner.cpp:3355, 771-777`).

Refusal checks on the CPU build (**LOCAL-OK**, each exits 1): `--gpu 0` (line 402, "built without CUDA support"),
`--gpu 0:1` (line 367, device list rejected), `--ingest compact` and `--ingest nvcomp` (line 245), `--ingest bogus` (line 163).

## 7. Real-format product campaign (UNRUN)

There is no single script for this. Reuse the existing pieces and declare unrun rows instead of widening the campaign:

- Corpus and hashes: `docs/workload_corpus/corpus.md`, `families.json`, `docs/workload_corpus/tools/fetch_corpus.py`, `docs/workload_corpus/tools/setup_corpus.py`
  (SHA-256 verified; 22 of 22 held-family files in the #186 pass).
- Tree comparison: `docs/issue85_laneC/compare_output_trees.py` with a manifest (`tutorial_24_movie_manifest.json` is the
  24-movie example). It validates each arm against the manifest, then compares MRC pixels, the extended header, STAR content
  and logs, normalising only the output root, duration lines and the MRC label date. **LOCAL-OK** on two CPU runs of the
  128 x 128 fixture (a manifest with `movies: ["Movies/..."]` and `expected_shape_xyz: [128,128,1]`): "Validated 1 movies, 1 MRC
  images, 2 STAR files, 16384 pixels per arm; Comparison: products; status=PASS; different files=0". Needs NumPy; movie names must
  carry the `Movies/` prefix the manifest expects.
- Per-row route proof: `--ingest_witness` plus a pinned `--ingest` where the row is meant to take one route.

Row template (run each row once per backend that can take it; arms must differ only in the backend):

```sh
./build-cuda/motioncorr --i movies.star --o "$OUT/<row>" --use_own --gpu 0 --j 8 \
    --ingest <auto|nvcomp|compact|float> --ingest_witness "$OUT/<row>.witness" <row options>
"$PY" docs/issue85_laneC/compare_output_trees.py --manifest <row manifest> --input-star movies.star \
    "$OUT/<baseline>" "$OUT/<row>"
```

| Row | Input | Route to prove (witness) | Options | Corpus family |
|---|---|---|---|---|
| R1 | TIFF 16-bit Deflate | `nvcomp` on the nvCOMP build; `compact` otherwise | gain, dose weighting, 5 x 5 patches | tutorial |
| R2 | TIFF 8-bit LZW BigTIFF | `compact` | gain or none, dose weighting | e10361, e10641, e10441 |
| R3 | MRC float32 | `float` | dose weighting | e10028 |
| R4 | MRC mode 0 (int8) and mode 1 (int16) | `compact` | dose weighting | e10164, e10216 |
| R5 | EER, grouping and upsampling 1 | `compact` | `--eer_grouping`, gain | e10474f3/f4, e12963 |
| R6 | EER with `eer_grouping` x (4 at upsampling -1, else 1) above 65535 | `float`, log line present | needs a movie with at least 3 x grouping fractions, so likely unreachable with real EER; if not run, declare UNRUN and cite the #196 overflow-guard control | synthetic |
| R7 | compressed MRC (`.mrc.zst` or similar) | `float` | needs the external decompressor | one small file |
| R8 | pinned-route refusals | movie fails, no completion STAR | `--ingest nvcomp` / `compact` on an ineligible movie | any ineligible movie |
| R9 | options | same-backend equality of each option arm with and without the option where defined | `--save_noDW`, `--even_odd_split`, `--bin_factor`, `--group_frames`, first/last frame, defect file, gain rot/flip | tutorial |
| R10 | direct input and glob | complete products | `--i 'Movies/*.tiff' --angpix --voltage` | tutorial subset |
| R11 | unchanged-setting resume | no reprocessing, identical tree | `--only_do_unfinished` | tutorial subset |
| R12 | one checked failure | named failure, no completion, healthy movies kept | truncated movie | one damaged copy |

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
single-process single-GPU run of the same input (`compare_output_trees.py`); **Ghostscript installed** (the aggregate renders
`logfile.pdf` strictly). Repeat at 1, 2 and 4 devices.

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
| Licence and notices review (#18: six ambiguous notices in `CPlot2D.cpp/.h` and four `src/acc/hip` headers) | maintainer | n/a | n/a | n/a | open | pending RC0 QF |

## 10. Tag procedure (do not execute from this draft)

1. Maintainer declares scope and frozen SHA (D4). Register items closed, CI green on that head.
2. QF evidence table complete, every row PASS or explicitly UNRUN/declared unsupported; the acceptance report filled and linked.
3. Re-check that the SHA being tagged equals the QF SHA (`git rev-parse HEAD`; no commits after the evidence).
4. Maintainer creates an annotated tag on that SHA, for example `git tag -a vX.Y.Z-rc0 <SHA> -m "RC0"`, and pushes it. Release notes
   link `SUPPORT.md`, the acceptance report, known limitations and D1/D2 outcomes.
5. After the tag, only the bug-fix policy in `POST_FREEZE_TEST_PLAN.md` applies.

No tag, release, merge or push to `main` is made by this document or its author.
