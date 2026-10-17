# RC0 evaluation candidate 2026-10-17: assembly, builds and routine regression

> [!IMPORTANT]
> **This is an evaluation candidate. It is not a frozen RC0, not a release and not fully qualified.**
> D4 (freeze scope and SHA) has not been taken. Under the QF runbook's verdict rules
> ([`../qf/README.md`](../qf/README.md#verdicts)), a run on a SHA that is not the frozen SHA is **UNRUN for
> QF**, so nothing here is a QF PASS. The results below are candidate results on the candidate source
> SHA only. Support status stays **evaluation**. The input-reader and recovery dispositions in
> [§8](#8-release-blockers-and-open-dispositions) remain open release blockers. Nothing here is merged, tagged
> or published. After Alex authorised it, the branch was pushed for testing as draft PR #227 (DO NOT MERGE).

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
| Hosted CI (added after push) | draft PR #227, run 39073675385 on the PR merge of `54d6b1ee`: Linux CTest 72/72 (pbzip2 case PASS), CUDA compile-only pass. This is not native CUDA evidence |
| Not run | pbzip2 case natively (hosted Linux CPU CTest only); item 15 (no D10 fix yet); QM, SCARF, timing |
| Release state | **not frozen, not fully qualified**: D10 (#221) and D11 (#226) fixes in progress (decided 2026-10-17: fix before freeze); D4 location decided as (a), the frozen SHA is a `main` commit; D3 merges, the freeze and QF pending (§8) |

## 1. Composition

The base is `main` at `71ab841e69869b615555bb02f8f393db59c22d73` (merge of #220). It includes #178, #185,
#187, #188, #200, #205, #210, #199, #217 and #220. Hosted CI ran on that commit: Linux CI run
[39042127102](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39042127102), success.

The four reviewed PR heads requested for this candidate were merged in this order with `git merge --no-ff`.
Every merge resolved automatically, with no conflict and no manual edit:

| Order | PR | Head merged | Content | Review state at that head | Hosted CI at that head |
|---|---|---|---|---|---|
| 1 | #223 macOS temp-dir test | `cd1f313b8eb765d6cd6c9bcb36e0b907b3caea0b` | one test line (`tests/test_tomography_endpoint.py`) | coordinator review: no findings | [39030283091](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39030283091) success |
| 2 | #202 input-format fixtures | `45516ff092f51b2e230a203d8e36e7b48e9a22eb` | test generators, tests, CMake test registration, required-test lists. Also `.github/workflows/ci.yml`: installs pbzip2/zstd and configures with `-DMC_REQUIRE_ALL_DECODERS=ON`. No `src/` | R-NEW round 2 resolved all round-1 findings on `2e88cf5b`. `45516ff0` merges main `483e881d` into the branch; the coordinator verified the net content was unchanged | [39029051194](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39029051194) success |
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
| Candidate source | **`adb3278542a33df1f3ae661d428c45d15a5a5b7f`**, branch `rc0-candidate-20261017-t3`. Pushed for testing (draft PR #227) after Alex authorised it. Hosted CI on this exact SHA: `workflow_dispatch` run [39075928389](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39075928389) on branch `rc0-candidate-20261017-t3-tested` (= `adb32785`), success (Linux CTest + CUDA compile-only; not native evidence) |
| Host checkout | `git clone` of a bundle of the branch (`rc0-candidate-adb32785.bundle`, sha256 `edc750c62740efecd7b01e02f96ca040da06f5ac679a9dc2a33f486c52578ba8`) into `$QF_W/src`. `HEAD = adb32785`, `git status --porcelain` empty at build time, at the start of each CTest batch and after all runs (`raw/end-state.txt`) |
| Harness | `docs/rc0/qf/tools/` at `adb32785` (= #224 `ef3e8f72`), copied to `$QF_W/tools/`. All 35 files hash-equal to the committed copies (`raw/tool-sha256.txt`). No tool, gate, threshold or required-test list was changed |
| Run drivers (not graders) | `raw/drivers/chainA.sh`, `chainB.sh`, `chainC.sh`, `collect_build_info.sh`. These only sequence the runbook commands, set the lane variables and record provenance |
| Reference binaries (comparison arms only) | Q1 CPU `1db86902` `dd86cd41…6b26439`; Q1 CUDA+nvCOMP `1db86902` `77db3f92…412a99`; Q1 `d7171b81` pre-#178 nvCOMP build and faultinject build `a8671c76…9d74` (hashes in the item JSONs) |
| Inputs | Corpus movies and gains are hashed against `docs/workload_corpus/corpus.md` by `product_campaign.py`: 7/7 movies and 2/2 gains match (`raw/campaign/summaries/inputs.json`). #123 matrix fixtures equal #123's recorded hashes (A4). The #208 damaged EER movies and the frozen synthetic recipe (`recipe_sha256 0c5fd2d0…`) regenerate to their recorded hashes. #207 and #204 real-data inputs are checked against their recorded hashes by the item drivers. #202's synthetic fixtures are generated inside CTest by `test-data/generate_format_fixtures.py` |

## 3. Build provenance (4GPUs, `tools/build.sh`)

Host `4-gpu-vm`, Ubuntu 24.04.4 LTS, kernel 6.8.0-136. 4× A100 80GB PCIe, driver 570.86.10. AMD EPYC 7452,
NUMA node 1 = CPUs 62–123. Full record: `raw/build/build-info.txt`.

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

- All three builds exited with rc 0 (`raw/build/build.out`). Each `CMAKE_HOME_DIRECTORY` is `$QF_W/src`.
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
| Bench lock | probed (`flock -n`) before every build, CTest batch and GPU run. It was never found held: all 114 occurrences of `bench_polls_held` in `raw/` are 0. They are 58 unique run records, plus 56 copies inside the three aggregate `summaries/all.json` files. The build log has no wait line, and no CTest `.waits` file was written |
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

- **Hosted CI (update after push, 2026-10-17 22:06Z).** Alex authorised the push. The branch was pushed without force at `54d6b1ee`, and draft PR [#227](https://github.com/KingAlejandro/MotionCorr-standalone/pull/227) (DO NOT MERGE) was opened.
  - Run [39073675385](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39073675385) checked out `b231c2d0`, i.e. `Merge 54d6b1ee into 71ab841e`. Its tree equals `54d6b1ee`, whose files outside `docs/rc0/candidate-20261017/` equal `adb32785`.
  - **Linux CTest: 72/72 pass**, including `InputFormats` `mrc_compressed_bz2` e2e PASS (pbzip2 installed, `MC_REQUIRE_ALL_DECODERS=ON`).
  - **CUDA compile-only: pass.**
  - Hosted CI is not native CUDA, performance or scientific evidence.
- **pbzip2-compressed MRC: UNRUN natively** on 4GPUs and macOS; hosted Linux CPU CTest covers it (above). pbzip2 is not installed, and `build.sh` does not set `MC_REQUIRE_ALL_DECODERS=ON`. No package was installed on the shared host.
- **Not covered here:**
  - Tier C launcher runs: covered only by the CTests that wrap it, as the runbook says (F2 applies).
  - Second venue (SCARF).
  - Tier D science.
  - Timing.
  - Genuine device poisoning (#213).
  - QM memory admission (separate, #225).
  - Item 15: N/A on this composition, which contains no D10 fix yet. On 2026-10-17 D10 was decided as fix before freeze; item 15 applies once the fix is composed.
- **Comparator scope:**
  - Strict all-files comparisons differ only in per-movie route log lines where the arms' routes differ. The declared route-log allowance is recorded and is not a gate.
  - For e10361 (u8 LZW), `--ingest auto` also logs `nvCOMP ingestion declined (bits per sample != 16)` before taking the compact route, so auto and pinned compact differ in that one log line.
  - Multi-GPU complete-tree comparisons differ only in per-movie log lines (thread count, free device memory), as in Q1; they are not a gate.
- `raw/macos/ctest-macos.summary.json` has `collected: null` because `summarize_ctest.py` parses the Linux CTest log format. The macOS collection validator reports 72 collected tests (`raw/macos/ctest-macos.log`), and the JUnit file has 72 test cases.
- `InputFormats` writes its generated fixtures under the system temporary directory (`/tmp/mc-formats-*`) rather than the workspace. This is test behaviour, recorded here; nothing was changed.

## 8. Release blockers and open dispositions

*Revised after the maintainer decisions of 2026-10-17 and the integration audit (R-INT-A/R-INT-B, §11). The
earlier version listed D10/D11 as "pending maintainer" and mixed decided documentation items in with blockers.*

**8.1 Open freeze blockers.** RC0 cannot be declared frozen or fully qualified until each is closed.

| ID | What | State |
|---|---|---|
| **D10 / EER-MS** ([#221](https://github.com/KingAlejandro/MotionCorr-standalone/issues/221)) | host EER decoder memory safety (all 65000/65001/65002 loops, container errors outside `omp critical`, TIFF tag checks, `readLegacy`), plus the MRC-header `abs(INT_MIN)` and `ltostr` arithmetic | **decided 2026-10-17: fix before freeze.** In progress (W-D10c, Gemini 4; as of the round-2 audit, not yet on origin and with no PR). Requires performance preservation (≥6 balanced pairs with AA null controls) and **two independent reviewers who did not author any D10 commit**: Claude Sonnet 5.5 and MiMo v2.6 Pro. Opus 5.5, Sol 6.1 and Gemini 4 all wrote D10 code. Compose only from the pushed origin head, by explicit SHA; the local ref `fix/rc0-d10-eer-memory-safety` at `486a51df` still has the collision. Runbook item 15 applies once it is composed. Composition must avoid the `render_eer` helper collision with #202 (§11, F-1) |
| **D11 / QM-D1** ([#226](https://github.com/KingAlejandro/MotionCorr-standalone/issues/226)) | stale `cudaErrorMemoryAllocation` after a handled OOM degrades the next movie's route (`auto`) or refuses it (pinned `--ingest nvcomp`) | **decided 2026-10-17: fix before freeze**, with no performance regression and no admission redesign. In progress as draft PR #228. Requires performance preservation (≥6 balanced pairs with AA null controls) and independent review by Sol 6.1, which wrote no D11 code. The body must not auto-close #226 ("Fixes #226" → "Refs #226"; requested from W-D11). `CudaStaleErrorAfterOom` must be in the required list or explicitly checked in QF |
| D3 | main merges, as merge commits pinned with `--match-head-commit`, with a tree-equality check after each | **#223, #202, #203, #224 merged 2026-10-17 (maintainer-approved): `ecb7d7f7`, `687ffc17`, `5e12fecf`, `1afa03b5`.** Main's tree after each merge equals the candidate's intermediate tree. Final main `1afa03b5` has tree `bd4742f7`, the same as `adb32785`, so the native evidence here applies to that tree. **Still to merge:** the D10 PR, #228 and #201, each after review and approval |
| D4 | freeze scope and frozen SHA | **Location decided 2026-10-17: option (a).** The frozen SHA is a `main` commit taken after the D3 merges. Its push CI is the D4 record's CI run. The SHA itself is not yet taken |
| QF | full audited QF on the frozen `main` SHA. It needs the D4 record, push CI on that exact SHA, item 15, item 10 in every shipped build, and an explicit check that `CudaStaleErrorAfterOom` was collected and passed | pending the fixes. **The runbook needs a small, independently reviewed update first:** item 15 still says "disposition PENDING", and there is no D11 check. That changes `docs/rc0/qf/`, so the tool hashes are re-recorded |
| REL ([#201](https://github.com/KingAlejandro/MotionCorr-standalone/pull/201)) | release docs | needs the freeze-time update and an independent R-REL re-review. At `34107d38` it still says #220 is pending merge, omits `CpuDoseSymmetryBase`, and describes D10 and D11 as open limitations. Under (a) it merges **before** the freeze, so `RELEASE_CHECKLIST.md` §10 ("no commits after the evidence") must allow later docs-only QF evidence commits and must say which commit is tagged. Its `src/` line citations must be re-checked against the composed tree. Two revisions (`cab5f620`, `34107d38`) have had no independent review since R-REL round 3 (`a31b4e03`) |
| #203 final fix | `0539bf52` (docs only) | **closed**: R-NEW round 3 (Claude Sonnet 5.5) CONFIRMED, no blocking findings ([comment](https://github.com/KingAlejandro/MotionCorr-standalone/pull/203#issuecomment-6242750071)). Three P3 wording notes remain open |

**8.2 Decided items handed off to the release docs.** Their dispositions are already decided, so none of these
blocks the freeze as a code change. Each must be stated correctly in #201.

| ID | Disposition |
|---|---|
| F4 / [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214) | D5: documented RC0 limitation (validate inputs with `xz -t`/`zstd -t`/`bzip2 -t`); fix after RC0. Item 13 shows the 6 KNOWN-F4 records unchanged |
| QM-D2/D3 (#226) | after RC0 (excluded from D11 by the maintainer); documented (DOC1, per-geometry VRAM floors) |
| E-1 / D6 | EER skip-and-warn and the truncated-EER shorter-movie behaviour are kept (D6); documented |
| [#215](https://github.com/KingAlejandro/MotionCorr-standalone/issues/215) | nvCOMP file-identity check deferred under D1 option 1 (trusted-input precondition) |
| C3, F2, DOC1, CMP1 (#216), #222, D2 | THP/allocator note, Tier C `--fixtures <scratch>` workaround, inherited host-memory behaviours, RELION 5.1 differences, macOS `rand()`, optional-SDK notice |
| S1 / D7 | evaluation RC0; no unrestricted CUDA local-alignment claim |
| Licence and notices (#18) | **D12, decided 2026-10-17: leave for later.** Not an RC0 freeze blocker; #201's checklist row must say it is deferred |
| F5, TST2 (#213) | big-endian mode-0 MRC with `nx=128` not swap-detected (document only); genuine device-poisoning control (post-RC0) |
| `metadata_table.cpp:1721` | `addToCPlot2D` reads `label2offset[EMDL_UNDEFINED]` (index −1) on the report-plot path. **D13, decided 2026-10-17: document for RC0, fix later**, tracked as [#229](https://github.com/KingAlejandro/MotionCorr-standalone/issues/229). It does not affect corrected products. D10's sanitizer controls use `--skip_report_pdf` to keep it out of the D10 evidence |

**8.3 Not a blocker; recorded.** #202's opt-in `RealCutdown` assets live in an external GitHub release
(`real-cutdown-v1`) that is still a draft. The test registers only when `MC_REAL_CUTDOWN_DIR` is set, and it is not in
the required list. Publishing the release would be a publication decision for Alex. Nothing here publishes it.

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

1. **D10 and D11 fixes:** finish them in their PRs, then independent review (D10: two reviewers; D11: Sol 6.1).
2. **Composition and reruns.** Tested compositions are built on the **`rc0-candidate-20261017-t3-tested`** line,
   starting from `adb32785`. Each reviewed fix is merged there by explicit origin SHA. That line has no candidate
   evidence docs, so its tree can be compared with the future `main` merges: equal, apart from #201. This branch
   (#227) then merges each tested composition and adds evidence-only commits. Every composition runs the **full**
   set (about 75 min); the round-2 audit showed a per-fix subset can miss inputs, e.g. item 8's mixed dataset
   contains an EER movie and item 12 reads MRC inputs. Before reruns, check the composed tree for duplicate test
   names, helper subcommands and required-list entries.
3. **D4 under decision (a)**, in this order:
   1. Reviewed fixes are composed and their reruns pass.
   2. #201 is updated (D10/D11 outcomes, #220, `CpuDoseSymmetryBase`, line citations, the tag/evidence rule) and
      re-reviewed by R-REL.
   3. The QF runbook update is reviewed.
   4. D3 merges go into `main` in candidate order, pinned with `--match-head-commit`, checking the tree after each.
   5. The frozen SHA F is the `main` commit after the last merge.
   6. Push CI runs on F.
   7. The full QF runs on F with the D4 record.
   8. QF results go into docs-only commits after F: `git diff F HEAD -- . ':!docs/rc0' ':!docs/release'` must be
      empty.
   9. The tag goes on the commit the maintainer and #201 name (F, or the evidence commit that cites F).
4. **#201:** the update above, before the freeze. The QF results are filled in afterwards, as evidence.
5. **Maintainer:** D3 approvals for the D10 PR, #228 and #201. Decided 2026-10-17: the first four D3 merges, D12 (licence/notices deferred) and D13 (#229 documented, fixed after RC0).

## 11. Integration audit (2026-10-17)

Two independent Gemini 4 auditors (R-INT-A `rc0-r-int-a-1`, R-INT-B `rc0-r-int-b-1`) were given an identical
read-only brief. Both returned **ON TRACK WITH ISSUES**. Both found:
- the composition, the merged heads' review state, every native result (including all 7 binary hashes) and the
  hosted-CI description supported;
- this README's push-status contradictions and stale §8;
- the stale #198 register, including row T3, which names #205's merge `f67a5866` instead of #217's `483e881d`;
- #201 drift;
- the frozen-SHA/CI sequencing question.

R-INT-B alone found **F-1 (P1)**: D10's `render_eer` test-helper subcommand collides silently with #202's helper
of the same name (`argc` 7 vs 6). The merge is textually clean, but in the composed tree D10's `EerMemorySafety`
would fail. The coordinator confirmed this with `git merge-tree` and asked the D10 worker to rename the helper and
test on the composed tree. R-INT-A alone noted that #198 asked for two D10 reviewers; that is adopted.

This revision fixes the README contradictions, the `raw/` paths, the macOS summary note, and §8/§10.

**Round 2.** Two more Gemini 4 auditors (R-INT-C/D) and two Claude Sonnet 5.5 auditors (R-INT-E/F) used one
identical brief. All four returned ON TRACK WITH ISSUES, with no open P1. All four confirmed:
- the round-1 fixes;
- run `39075928389` on exactly `adb32785`;
- that merging the four PRs into `71ab841e` reproduces tree `bd4742f7` in any order;
- that #228 composes cleanly;
- that the helper collision is fixed only in the local `w-d10c` (`9cc45d1a`).

The remaining findings are adopted in §8.1, §8.2 and §10:
- conflicts with decision (a) (#201 ordering and the checklist tag rule);
- D10 reviewer independence (Sol authored D10 code);
- the licence/notices row;
- the #228 auto-close keyword;
- the required-list status of `CudaStaleErrorAfterOom`;
- the runbook item 15/D11 update;
- the full rerun set;
- building tested compositions on the `-tested` line;
- the `bench_polls_held` count wording;
- the #202 `ci.yml` delta;
- `metadata_table.cpp:1721`.
