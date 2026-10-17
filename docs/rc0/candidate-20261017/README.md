# RC0 evaluation candidate 2026-10-17: assembly, builds and routine regression

> [!IMPORTANT]
> **This is an evaluation candidate. It is not a frozen RC0, not a release and not fully qualified.**
> D4 (freeze scope and SHA) has not been taken. Under the QF runbook's verdict rules
> ([`../qf/README.md`](../qf/README.md#verdicts)), a run on a SHA that is not the frozen SHA is **UNRUN for
> QF**, so nothing here is a QF PASS. The results below are candidate results on the candidate source
> SHA only. Support status stays **evaluation**. The input-reader and recovery dispositions in
> [§8](#8-release-blockers-and-open-dispositions) remain open release blockers. Nothing here was pushed, merged,
> tagged or published.

Requested by Alex (issue #198 programme, release engineering). Work package: candidate assembly, builds
and routine CPU/CUDA/nvCOMP regression checks from the audited QF runbook. The input-reader and recovery
fixes are out of scope here, and so are their specialist test campaigns.

## Outcome at a glance

| Category | Result on candidate `adb32785` |
|---|---|
| Candidate assembly | main `71ab841e` + #223 + #202 + #203 + #224 at their reviewed heads. Clean automatic merges; no `src/` delta over main |
| Builds | CPU, CUDA sm80 and CUDA sm80+nvCOMP: 3/3 rc 0, Release `-O3 -DNDEBUG`, binaries hashed |
| CPU regression (CTest CPU, Tier A) | 72/72, 0 skipped; collection validator and fail-closed controls pass |
| Native CUDA / CUDA+nvCOMP CTest | 105/105 and 108/108, 0 skipped (GPU0 and GPU1, UUID-pinned) |
| Same-backend identity | route invariance 14/14; CPU vs Q1 CPU 14/14 strict; #178 6/6 + injected fallback; #123 matrix 16/16 ×2; EER #208 replay 41/41 + powered controls; resident retry 4/4 + dataset; MRC #204 harness PASS; multi-GPU G/L 1/2/4 workers and mixed format identical |
| CPU/CUDA diagnostic (Tier B) | recorded, not graded; S1 values unchanged from Q1 |
| Scientific validation (Tier D) | not run; no claim |
| macOS | builds and runs; not qualified; 70/72 (`SyntheticRegression` #222 fails, `NativeMovieStaging` skipped) |
| Not run | hosted CI on this SHA (not pushed); pbzip2 cases; item 15 (D10 undecided); QM, SCARF, timing |
| Release state | **not frozen, not fully qualified**: D10 (#221) and D11 (#226) open, D4 not taken |

## 1. Composition

The base is `main` at `71ab841e69869b615555bb02f8f393db59c22d73` (merge of #220). It includes #178, #185,
#187, #188, #200, #205, #210, #199, #217 and #220. Hosted CI ran on that commit: Linux CI run
[39042127102](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39042127102), success.

The four reviewed PR heads requested for this candidate were merged in this order with `git merge --no-ff`.
Every merge resolved automatically, with no conflict and no manual edit:

| Order | PR | Head merged | Content | Review state at that head | Hosted CI at that head |
|---|---|---|---|---|---|
| 1 | #223 macOS temp-dir test | `cd1f313b8eb765d6cd6c9bcb36e0b907b3caea0b` | one test line (`tests/test_tomography_endpoint.py`) | coordinator review: no findings | [39030283091](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39030283091) success |
| 2 | #202 input-format fixtures | `45516ff092f51b2e230a203d8e36e7b48e9a22eb` | test generators, tests, CMake test registration, required-test lists; no `src/` | R-NEW round 2 resolved all round-1 findings on `2e88cf5b`. `45516ff0` merges main `483e881d` into the branch; the coordinator verified the net content was unchanged | [39029051194](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39029051194) success |
| 3 | #203 format-coverage docs | `0539bf523f125b70a9d4349e77d910e3c3b382db` | `docs/workload_corpus/**` only | R-NEW round 2 left one P2. It was fixed in `0539bf52`, and the coordinator accepted the fix. **No independent round-3 re-review is recorded** | [39029073734](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39029073734) success |
| 4 | #224 QF runbook and tooling | `ef3e8f72a98c56404a02a5f5708ef09ec5734391` | `docs/rc0/qf/**` (runbook, tools, rehearsal evidence) | R-QF round 3: **fit for QF**, no blocking findings | [39040505351](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39040505351) success |

Candidate merge commits: `02852b67` (#223), `3cf96e02` (#202), `be4af664` (#203), `adb32785` (#224).

**Composition check:**
- `git diff 71ab841e adb32785 -- src` is empty.
- Every other changed file has the same blob as the one PR head that changes it, with three exceptions: `CMakeLists.txt`, `tools/test_ci_fail_closed.py` and `tools/validate_test_collection.py`. For each of these, the candidate's added and removed lines over main are identical to #202's delta over its base `483e881d`.
- The candidate is therefore main plus exactly the four reviewed deltas.

**Not in the candidate:**
- #201 (release docs, pending freeze-time updates) and #225 (QM evidence). Neither was requested.
- Every parked or NO-GO item in #198: #206, #211, #219, #181/#182, L1.
- Any fix for D10/D11 (§8).

## 2. Revisions

| What | Revision |
|---|---|
| Candidate source | **`adb3278542a33df1f3ae661d428c45d15a5a5b7f`**, branch `rc0-candidate-20261017-t3`. Local only: **not pushed, so no hosted CI exists for this SHA** |
| Host checkout | `git clone` of a bundle of the branch (`rc0-candidate-adb32785.bundle`, sha256 `edc750c62740efecd7b01e02f96ca040da06f5ac679a9dc2a33f486c52578ba8`) into `$QF_W/src`. `HEAD = adb32785`, `git status --porcelain` empty at build time, at the start of each CTest batch and after all runs (`raw/end-state.txt`) |
| Harness | `docs/rc0/qf/tools/` at `adb32785` (= #224 `ef3e8f72`), copied to `$QF_W/tools/`. All 35 files hash-equal to the committed copies (`raw/tool-sha256.txt`). No tool, gate, threshold or required-test list was changed |
| Run drivers (not graders) | `raw/drivers/chainA.sh`, `chainB.sh`, `chainC.sh`, `collect_build_info.sh`. These only sequence the runbook commands, set the lane variables and record provenance |
| Reference binaries (comparison arms only) | Q1 CPU `1db86902` `dd86cd41…6b26439`; Q1 CUDA+nvCOMP `1db86902` `77db3f92…412a99`; Q1 `d7171b81` pre-#178 nvCOMP build and faultinject build `a8671c76…9d74` (hashes in the item JSONs) |
| Inputs | Corpus movies and gains are hashed against `docs/workload_corpus/corpus.md` by `product_campaign.py`: 7/7 movies and 2/2 gains match (`raw/campaign/summaries/inputs.json`). #123 matrix fixtures equal #123's recorded hashes (A4). The #208 damaged EER movies and the frozen synthetic recipe (`recipe_sha256 0c5fd2d0…`) regenerate to their recorded hashes. #207 and #204 real-data inputs are checked against their recorded hashes by the item drivers. #202's synthetic fixtures are generated inside CTest by `test-data/generate_format_fixtures.py` |

## 3. Build provenance (4GPUs, `tools/build.sh`)

Host `4-gpu-vm`, Ubuntu 24.04.4 LTS, kernel 6.8.0-136. 4× A100 80GB PCIe, driver 570.86.10. AMD EPYC 7452,
NUMA node 1 = CPUs 62–123. Full record: `raw/build-info.txt`.

| Toolchain / dependency | Version |
|---|---|
| Compiler | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0; glibc 2.39 |
| CUDA | nvcc 12.8.61 (`/usr/local/cuda-12.8`), `-DCMAKE_CUDA_ARCHITECTURES=80`, cuFFT 11 / cudart 12 from 12.8 |
| nvCOMP | 5.3.0.16 (`~/nvcomp53/…_cuda12-archive`, optional SDK, not vendored, D2) |
| CMake / Python / NumPy | 3.28.3 / 3.12.3 / 2.5.3 (`~/.mc-venv`) |
| FFTW | 3.3.10 (libfftw3-dev 3.3.10-1ubuntu3) |
| LibTIFF | 4.5.1 (4.5.1+git230720-4ubuntu2.5); Deflate subcodec libdeflate 1.19 |
| zlib / libpng / libjpeg / zstd | 1.3 / 1.6.43 / turbo 2.1.5 (libjpeg8) / 1.5.5 |
| OpenMP | GCC libgomp 14.2.0 (OpenMP 4.5) |
| Ghostscript | 10.02.1 |
| THP / `GLIBC_TUNABLES` | `madvise` / unset |
| Decoders on PATH | xz, bzip2, zstd present; **pbzip2 absent** (see §7) |

| Build | Configure | `motioncorr` sha256 | `motioncorr_faultinject` | `motioncorr_resident_retry_fault` | CTest collected |
|---|---|---|---|---|---|
| CPU | `-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF` | `ca98c23aff8ff02cc3f954c32daaedd5a550edf607b797a50b60d3ab4fb9e2e2` | — | — | 72 |
| CUDA sm80 | `… -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=OFF` | `9f6839a2b85e421f42fa8ddb3c487030434e5fa317917a8da1e8bc29c3cba7bd` | `25fb87d1…993b1d` | `15fce418…356ec6` | 105 |
| CUDA sm80 + nvCOMP | `… -DUSE_NVCOMP=ON -DNVCOMP_ROOT=…5.3.0.16_cuda12-archive` | `43c4ca0dcfff13b8fb3d4653844415e333e5eb4ea7a8d0e01b76b1f0cb6160ae` | `d1302dd2…48692a` | `b7efe25d…d8d002` | 108 |

- All three builds exited with rc 0 (`raw/build.out`). Each `CMAKE_HOME_DIRECTORY` is `$QF_W/src`.
- **Flags:**
  - C++ in every build: `-O3 -DNDEBUG -std=gnu++17 -fopenmp`.
  - CUDA: `-O3 -DNDEBUG -std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80] -Xcompiler -fopenmp`.
  - No `-march`, `-mfma` or other FMA flag.
- **Item 10 (#220):** `MOTIONCORR_CPU_DOSE_SYMMETRY=AUTO`. Each build's configure reports `CPU dose weighting: symmetric rows (AUTO: qualified x86-64 GCC without FMA)` and defines `MOTIONCORR_CPU_DOSE_SYMMETRY_MODE=2`. This matches #220's qualified-toolchain contract.

## 4. Resources

| | |
|---|---|
| Lane A | GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54` pinned by UUID, CPUs 96–103 (`taskset`), `/tmp/motioncorr-gpu0-correctness.lock` held per batch or per run by the tools |
| Lane B | GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` pinned by UUID, CPUs 104–111, `/tmp/motioncorr-gpu1-correctness.lock` |
| CPU CTest | lane B CPUs 104–111, no GPU |
| Multi-GPU window | all four `gpuN-correctness` locks (ascending) and then the bench lock, held by `multigpu_step.sh` from 19:20:45Z to 19:25:00Z in three invocations, after confirming no compute process on any GPU. Workers on GPU0–3 by UUID; 16-CPU budget 96–103 + 104–111 |
| Bench lock | probed (`flock -n`) before every build, CTest batch and GPU run. It was never found held: 114/114 run records carrying the field show `bench_polls_held 0`, the build log has no wait line, and no CTest `.waits` file was written |
| Occupancy at start (18:21Z) | all four GPUs idle with no compute process; every `/tmp/motioncorr-*.lock` free. No other MotionCorr job was running; another user's interactive editor session was left alone |
| Scratch | `/mnt/clathrin/alex-motioncorr-rc0/W-RC0-CAND` (5.0 GB at the end, bulk MRC outputs deleted by the tools after grading). Programme directory 49 GB at start, 54 GB at end, against the 300 GB limit. `/mnt/clathrin` had 1.2 TB free |
| macOS | local Apple M4 Pro, macOS 26.7.1, AppleClang 21.0.0, CMake 4.4.4, `-j6`, scratch `/tmp/rc0cand` |

This is correctness work only: **no timing or performance claim** is made, and no timing campaign was started.
Wall times in the logs are incidental.

## 5. Results by category

The categories are kept separate, as `docs/gate_contract.md` requires. A PASS in one category says nothing about the others.

### 5.1 CPU regression and build checks (Tier A and unit/contract CTests)

| Runbook item | Command | Result on `adb32785` |
|---|---|---|
| 0 builds | `bash tools/build.sh` | 3/3 rc 0 (§3) |
| 1 CTest CPU | `bash tools/run_ctest.sh cpu` | **72/72 passed, 0 failed, 0 skipped**. `validate_test_collection` PASS (72 collected), `test_ci_fail_closed.py -v` rc 0. Load-sensitive `ProfilingKit` passed on its first run; no rerun was used |
| 4 F3/F3b (#205), CPU part | inside item 1 | `TruncatedMrcMovie`, `TruncatedGainDefect` passed |
| 10 `CpuDoseSymmetry` / `CpuDoseSymmetryBase` | inside items 1–3 | both collected (required) and passed in **all three builds**. The selected path is `symmetric` (AUTO), forced base `original`; 1,681 exact-bit cases each |
| #202 tests | inside items 1–3 | `InputFormats` and `CutDownMovie` passed in all three builds. `InputFormats`: 114 cases (89 accept, 18 reject, 5 characterise, 1 known failure); `mrc_compressed_bz2` **UNRUN (pbzip2 absent)**; `eer_legacy_container` NOT RUN by design |

### 5.2 CUDA and nvCOMP native checks (same-backend contracts, failure/publication semantics)

| Runbook item | Command | Result on `adb32785` |
|---|---|---|
| 2 CTest CUDA | `bash tools/run_ctest.sh cuda` (lane A) | **105/105 passed, 0 skipped**, validator PASS, lane GPU witnessed (UUID pin + lock) |
| 3 CTest CUDA+nvCOMP | `bash tools/run_ctest.sh nvcomp` (lane B) | **108/108 passed, 0 skipped**, validator PASS. Includes the #217 decline/boundary tests (`NvcompGuards`, `CudaNvcompAcceptanceFailures`, …) and `CudaResidentRetryFailures` natively |
| 4 F3/F3b, CUDA part | inside items 2–3 | `TruncatedMrcMovieCuda`, `TruncatedGainDefectCuda` passed in both CUDA builds |
| 9 adapted #123 matrix | `run_compact_ingest_support_matrix.py --binary build-{nvcomp,cuda}/motioncorr --device $QF_GPU_UUID` | **16/16 rows PASS on both CUDA executables** (rc 0). 28/28 arms on each were seen by nvidia-smi on the lane UUID only. Routes: 23 compact, 16 float, as declared. Gain-effect control `differs: true`. The JSON records source `adb32785`, 0 modified files, the binary hash and the #123 harness, comparator and fixture hashes |
| 11 EER compact (#208 replay) | `item11_eer.py --negative-controls`; `item11_noguard_control.sh` | **41/41 replayed cases PASS, 0 FAIL, 0 UNRUN** (heavy up2-F4/up3 cases included). o1n is N/A in the main pass and is replaced by the guard-removed control, as in the rehearsal. 4/4 negative controls rejected. Guard-removed control: the mutant build `5cb3f1fa…` gives **o1n and o5n PASS**, with compare rc 1 (compact ≠ float without the guard, so the fixtures reach the wrap). Synthetic recipe `0c5fd2d0…` regenerated to its recorded hashes. CPU arms are identical to Q1 CPU `1db86902` |
| 12 resident retry (#207), single GPU | `item12_retry.py` (lane B) | **4/4 single-GPU cases PASS.** Retried counts are e10641 g1 41, e10641 g4 9, e10216 g1 30 and e10216 g4 25 (#207's values), each equal to the shim counter. Recoverable arm: one warning, products identical. Fatal arm: rc 1 with refusal, nothing published. remaining-owned 0. Frozen vs Q1 CUDA+nvCOMP `1db86902` and frozen vs counter run: full and products-only identical |
| 12 resident retry, dataset part | `multigpu_step.sh --driver item12_retry.py --dataset` | **dataset PASS** (GPU0 + GPU1). d1, d2 and dshim healthy and identical (30 files), with the dshim counter equal to retried. dpoison: #207's asymmetric case through `qf_fault_by_uuid.sh` (`260a79b8…`), `fault=on` only for GPU1's worker. Worker rcs [0, 1], dataset not ready, rc 3, nothing merged. dpoison_both: worker rcs [1, 1]. Status files, device witness and cleanup present for every arm |
| 13 raw integer MRC (#204 harness) | `item13_mrc.sh` (lane B) | **grade PASS, driver rc 0.** 14 runs, each with the recorded count and 0 verdict mismatches against #204 (matrix 36+36, refuse 2, compressed 49, options 10, errors 26+26, real 6, option runs 10). Both `errors` runs pass 26/26 (#205). The 6 F4 `damaged` records stay FAIL, listed as KNOWN-F4 (#214). Real-data inputs match #204's hashes. 356 invocations, every one logged with the frozen binary hash (294 CUDA+nvCOMP, 62 CPU) |
| 8 multi-GPU publication 1/2/4 workers | `multigpu_step.sh --configs G,L`; `multigpu_step.sh --mixed` | **G and L: w1, w2 and w4 rc 0, `problems []`.** The single-process reference s0 (GPU0 by UUID pin; the harness takes no device witness for it) exited with rc 0. Every launcher arm passes the dataset contract checks: `dataset_ready`, `aggregate_pass`, `workers_pass`, shards disjoint and covering the input, worker products matching a shard, joint-STAR row order equal to the input, `logfile.pdf` present, worker aggregates diverted, no leftover processes. Workers ran on distinct GPU UUIDs, w4 on GPU0–3. **All 6 arm pairs per config are identical** (identity lib PASS, `--products-only` rc 0). The positive untouched-copy control PASS and the flipped-payload-byte control FAIL in both comparators. **Mixed format (tutorial + 10641 + Falcon3 EER): w1 and w2 rc 0, `problems []`, identical.** Complete-tree comparisons (full_rc 1) differ only in per-movie log lines, as in Q1; they are not a gate |

### 5.3 Same-backend output identity

| Runbook item | Result on `adb32785` |
|---|---|
| 5 route invariance, 7 families × G/L | **14/14 cases PASS** (7 families × G/L, `--ingest auto/compact/float` + CPU + Q1 CPU reference). Products-only identity: every compact and float arm is identical to auto. e10028 (float MRC): pinned compact is **refused**, as expected, and publishes nothing. Every GPU arm was witnessed on the lane GPU only. Auto routes: tutorial nvCOMP; 10361, 10474-F3, 12963, 10216 and 10164 compact; 10028 float |
| 6 CPU identity vs Q1 `1db86902` | **14/14 identical** to Q1's CPU `1db86902` (`dd86cd41…6b26439`), both products-only **and** strict all-files. This is the expected result: #220 claims bit-identical CPU output, and the CPU build here runs the symmetric dose path (AUTO). No expected-difference case was needed |
| 7 #178 CPU unweighted path | **6/6 cases identical to pre-#178 `d7171b81`**: noDW G/L, even/odd G/L, even/odd with 23 frames L, and no dose weighting G (CUDA+nvCOMP build without `--gpu`, CPU line witnessed). **Injected recoverable `cudaMalloc` failure:** ordinal 16 of 19 reaches the CPU line after the device reconstruction is announced. Its products are identical to the pre-#178 faultinject build (`a8671c76…`) at the same ordinal |
| CUDA identity vs Q1 CUDA `1db86902` | in item 12: frozen vs Q1 CUDA+nvCOMP `1db86902` identical on all four single-GPU cases (#207's "db" arm) |

Campaign detail (`raw/campaign/summaries/`; table generated by `raw/drivers/summarize_candidate.py` from the tool's own JSON; every verdict is `product_campaign.py`'s):

| case | routes auto/compact/float | auto vs compact (products) | auto vs float (products) | strict all-files, declared route-log allowance | CPU vs Q1 CPU `1db86902` products / strict | Tier B relative image RMSE vs CPU (diagnostic only, never graded) | campaign verdict |
|---|---|---|---|---|---|---|---|
| e10028 G | float/refused (expected)/float | — | PASS | — ; PASS/PASS | PASS / PASS | 0.01392 | PASS |
| e10028 L | float/refused (expected)/float | — | PASS | — ; PASS/PASS | PASS / PASS | 0.01401 | PASS |
| e10164 G | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.001494 | PASS |
| e10164 L | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.001252 | PASS |
| e10216 G | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.01659 | PASS |
| e10216 L | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.4344 | PASS |
| e10361 G | compact/compact/float | PASS | PASS | FAIL/PASS ; FAIL/PASS | PASS / PASS | 0.01095 | PASS |
| e10361 L | compact/compact/float | PASS | PASS | FAIL/PASS ; FAIL/PASS | PASS / PASS | 0.009091 | PASS |
| e10474f3 G | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.01555 | PASS |
| e10474f3 L | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.5999 | PASS |
| e12963 G | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.02273 | PASS |
| e12963 L | compact/compact/float | PASS | PASS | PASS/PASS ; FAIL/PASS | PASS / PASS | 0.499 | PASS |
| tutorial G | nvcomp/compact/float | PASS | PASS | FAIL/PASS ; FAIL/PASS | PASS / PASS | 0.007096 | PASS |
| tutorial L | nvcomp/compact/float | PASS | PASS | FAIL/PASS ; FAIL/PASS | PASS / PASS | 0.008358 | PASS |

Input hashes vs `docs/workload_corpus/corpus.md`: tutorial: movie match, gain match; e10361: movie match; e10474f3: movie match; e12963: movie match, gain match; e10216: movie match; e10028: movie match; e10164: movie match

### 5.4 CPU/CUDA diagnostics (Tier B, recorded and never graded)

The CPU-vs-CUDA `compare_motioncorr.py --gate backend` values (table above, last column) are **recorded only, never graded**; they are not an acceptance result. Relative image RMSE, config L: 10474-F3 **0.5999**, 12963 **0.4990**, 10216 **0.4344**; tutorial 0.00836, 10361 0.00909, 10164 0.00125, 10028 0.0140. Config G: 0.0015–0.0227. These equal Q1's recorded S1 values at `1db86902` (0.600 / 0.499 / 0.434; G 0.0015–0.023). The values match to the rounding shown; this is not a byte comparison. S1 is unchanged by the composition, and no threshold was touched.

### 5.5 Scientific validation (Tier D)

**Not run; no claim.** No CTF, FSC or B-factor evidence (#61) was produced. Nothing here establishes scientific
equivalence between the backends, or a preference for either. S1/D7 stands as decided: evaluation RC0, and no
unrestricted CUDA local-alignment claim.

## 6. macOS (runbook item 14, reported separately, not a qualification)

Clean clone of `adb32785` on Apple M4 Pro, macOS 26.7.1, AppleClang 21.0.0, `cmake -DCMAKE_BUILD_TYPE=Release
-DBUILD_TESTING=ON`. Configure reports `CPU dose weighting: original loop (AUTO: AppleClang on arm64 …)`, as
#220's contract requires. `motioncorr` sha256 `3dff5d11714d54330ee1fc15ba161f5a207331014cbe2c6bea364989bd39cbc5`.

- `validate_test_collection` PASS (72 collected); `test_ci_fail_closed.py -v` rc 0.
- CTest: **70 passed, 1 failed, 1 skipped**.
  - `SyntheticRegression` failed: max pixel difference 23.65 vs the Linux baseline. This is the known libc `rand()` hot-pixel difference, #222.
  - `NativeMovieStaging` was skipped.
  - `MultiGpuScheduling` **passed** (#223 is in the candidate).
  - `CpuDoseSymmetry`/`Base` passed, both on the original path (AUTO selects original here, so the symmetric code is not exercised on this platform). Both report `exact complex bits PASS; exp-call bound SKIPPED (no witness)`; on Linux both report `exact complex bits and exp-call bound PASS`.
  - `InputFormats` passed, with the pbzip2 case UNRUN.
- Source tree clean after the run. Statement: **"macOS arm64: builds and runs; not qualified; known CPU CTest
  differences"** (`raw/macos/`).

## 7. Not run, limitations and observations

- **Hosted CI on `adb32785`: UNRUN.** The branch was not pushed. Every constituent head and the base has green CI, but the composed SHA has none. Pushing the branch, or opening a draft PR, needs Alex's go-ahead.
- **pbzip2-compressed MRC: UNRUN** on 4GPUs and macOS. pbzip2 is not installed, and `build.sh` does not set `MC_REQUIRE_ALL_DECODERS=ON`. Hosted CI installs pbzip2 and sets that flag, so it would cover these cases once the branch is pushed. No package was installed on the shared host.
- **Not covered here:**
  - Tier C launcher runs: covered only by the CTests that wrap it, as the runbook says (F2 applies).
  - Second venue (SCARF).
  - Tier D science.
  - Timing.
  - Genuine device poisoning (#213).
  - QM memory admission (separate, #225).
  - Item 15: N/A while D10 is undecided (no fix in the candidate).
- **Comparator scope:**
  - Strict all-files comparisons differ only in per-movie route log lines where the arms' routes differ. The declared route-log allowance is recorded and is not a gate.
  - For e10361 (u8 LZW), `--ingest auto` also logs `nvCOMP ingestion declined (bits per sample != 16)` before taking the compact route, so auto and pinned compact differ in that one log line.
  - Multi-GPU complete-tree comparisons differ only in per-movie log lines (thread count, free device memory), as in Q1; they are not a gate.
- `InputFormats` writes its generated fixtures under the system temporary directory (`/tmp/mc-formats-*`) rather than the workspace. This is test behaviour, recorded here; nothing was changed.

## 8. Release blockers and open dispositions

The candidate contains none of the following. Each one keeps RC0 from being declared frozen or fully qualified, or
from describing the input paths as stable, until its disposition is resolved:

| ID | Issue | Area | State |
|---|---|---|---|
| **D10 / EER-MS** | [#221](https://github.com/KingAlejandro/MotionCorr-standalone/issues/221) | input reader (host EER decoder): heap OOB **write** and read on malformed or truncated EER, `REPORT_ERROR` inside `omp critical` aborts the process; MRC header `abs(INT_MIN)` UB | confirmed (W-EER-DEV ASan, V-EER independent verification). **Disposition pending maintainer.** The coordinator recommends (a), a narrow pre-freeze fix. Until resolved, the EER input path is not stable (runbook item 15) |
| **D11 / QM-D1** | [#226](https://github.com/KingAlejandro/MotionCorr-standalone/issues/226) | recovery: stale `cudaErrorMemoryAllocation` after an OOM in `cudaAlignPatch` is not cleared. The next movie falls back under `auto`, and is **refused** under pinned `--ingest nvcomp` | traced at source (R-QM). **Disposition pending maintainer**: (a) document and fix post-RC0, or (b) small pre-freeze fix with a two-movie native control |
| F4 | [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214) | input reader (compressed MRC): decoder exit status ignored | D5: documented RC0 limitation (validate inputs with `xz -t`/`zstd -t`/`bzip2 -t`). The fix is scheduled post-RC0; item 13 shows the 6 KNOWN-F4 records unchanged |
| QM-D2/D3 | #226 | admission gap (config L), late misleading OOM | post-RC0, documented (DOC1) |
| E-1 / D6 | — | damaged EER fractions skipped with a warning | preserved by decision D6; documentation hand-off to #201 |
| #215 | [#215](https://github.com/KingAlejandro/MotionCorr-standalone/issues/215) | nvCOMP file-identity check between tag scan and strip read | deferred post-RC0 under D1 option 1 (trusted-input precondition) |
| D4 | #198 | freeze scope and SHA | not taken; this candidate is input to that decision |
| REL | #201 | release docs | merge-ready draft. It still needs the freeze-time updates (QF results, #223 inclusion, D10/D11 outcomes, DRAFT labels) |

S1/D7 is decided and is not a blocker for an *evaluation* RC0. It does block any unrestricted CUDA local-alignment claim.

## 9. Reproduce

On 4GPUs, from `$QF_W` (`raw/drivers/` holds the exact scripts):

```sh
export QF_W=/mnt/clathrin/alex-motioncorr-rc0/W-RC0-CAND QF_SHA=adb3278542a33df1f3ae661d428c45d15a5a5b7f
# lane A
export QF_CPUS=96-103 QF_GPU_UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 QF_GPU_LOCK=/tmp/motioncorr-gpu0-correctness.lock
bash tools/build.sh
bash tools/run_ctest.sh cuda
QF_W=$QF_W flock $QF_GPU_LOCK taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/run_compact_ingest_support_matrix.py \
  --binary build-nvcomp/motioncorr --device $QF_GPU_UUID --workdir matrix-nvcomp --json matrix-nvcomp.json   # and build-cuda
QF_REF_CPU_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/product_campaign.py
taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item11_eer.py --negative-controls; bash tools/item11_noguard_control.sh
# lane B
export QF_CPUS=104-111 QF_GPU_UUID=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d QF_GPU_LOCK=/tmp/motioncorr-gpu1-correctness.lock
bash tools/run_ctest.sh cpu; bash tools/run_ctest.sh nvcomp
bash tools/item13_mrc.sh; taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item12_retry.py
taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/fallback178.py; taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/fallback178_injected.py
# multi-GPU window (lane A variables plus)
export QF_MG_CPU_A=96-103 QF_MG_CPU_B=104-111 QF_MG_W1_GPU=0 QF_DATASET_GPU2_UUID=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d QF_DATASET_CPUS2=104-111
bash tools/multigpu_step.sh --configs G,L; bash tools/multigpu_step.sh --mixed
bash tools/multigpu_step.sh --driver item12_retry.py --dataset
```

`fallback178*.py` run after `product_campaign.py` has finished, because both rebuild `$QF_W/dataroot` and
`$QF_W/inputs/<family>` symlinks.

## 10. Next steps

1. **Hosted CI on the composed SHA (needs Alex).** Push `rc0-candidate-20261017-t3`, or open it as a draft PR
   that is never merged, so Linux CI and CUDA compile-only run on `adb32785`. This also exercises the pbzip2
   cases. Until then hosted CI is UNRUN for this SHA.
2. **D10 (#221) and D11 (#226) dispositions (maintainer).** Approved fixes land as their own PRs, with their own
   reviews and specialist campaigns (outside this package). A new candidate then composes them, and this package
   is repeated on it, plus runbook item 15. Measured compute for this package: builds 6 min; three CTest suites
   15 min across two lanes; items 5–13 about 45 min; the multi-GPU window 4.3 min.
3. **Main merges (maintainer, D3).** #223, #202, #203 and #224 are each merge-ready on their own heads. If they
   are merged into `71ab841e` in this order without further changes, the resulting tree should equal this
   candidate's tree `bd4742f70d7118d6006ceb465e3bcd1947ed4167` (`git rev-parse <sha>^{tree}`). That would tie
   the evidence here to a main commit. QF itself must still run on the frozen SHA.
4. **D4 and QF proper.** After the blockers are resolved and the freeze SHA is chosen, run the full runbook on it
   with the D4 record, the frozen-binary reruns and the GitHub Actions run on that SHA. This candidate run shows
   the current composition is green on the runbook's correctness items; it does not replace QF.
5. **#201 freeze-time updates (W-REL):** QF results, #223 inclusion (the macOS statement now has
   `MultiGpuScheduling` passing), the D10/D11 outcomes and the DRAFT labels.
6. Optional: an independent confirmation of #203's final P2 fix (`0539bf52`, docs only). The coordinator accepted
   it, but no round-3 review is recorded.
