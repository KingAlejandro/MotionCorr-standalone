# RC0 final qualification (QF) on F = `6d68e2d6`: report and D4 record

**Result:** 16 of the 17 QF items PASS on F. Item 13 is **FAIL** under its frozen criterion, from one case
whose behaviour changed because of the D10 header fix (#231). It is dispositioned by hand below. Item 14
(macOS) is reported separately and is not graded. CTest counts are 74/108/111, `d11.case = with_d11`, and
no test failed, was skipped or was not run.

The run follows [`../README.md`](../README.md) as it stands on F, with the committed tools. Raw records are
in [`raw/`](raw/).

## D4 freeze record

| Element | Record |
|---|---|
| Frozen SHA (D4 = a) | F = `6d68e2d6ec45c37b75fd0f4aaff8272f192b7029` (#201 merge; same source as the #228 merge `e3871ca2`; #198 comment 6256406171) |
| QF checkout | `/mnt/clathrin/alex-motioncorr-rc0/W-QF/src`, a git clone checked out at F. `git rev-parse HEAD` = F, and `git status --porcelain` is empty at build time (`raw/logs/build.out`, `raw/ctest-*.log` headers) and at the end of the run (`raw/end-state.txt`) |
| Tools | `$QF_W/tools/` copied from F's `docs/rc0/qf/tools/`. The sha256 of every file (`raw/tool-sha256.txt`, 38 files) equals the committed tools at F |
| Binaries | `raw/binaries.sha256`; table below |
| Push CI on F | run 39175914447, push event, **success** (Build & Smoke Check (Ubuntu Linux), CUDA compile only). Compile-only CUDA is not native evidence |
| Host and toolchain | 4GPUs (`4-gpu-vm`, kernel 6.8.0-136), 4 × A100 80GB PCIe, driver 570.86.10, CUDA 12.8.61, g++ 13.3.0, Python 3.12.3 + NumPy 2.5.3 (`~/.mc-venv`), Ghostscript 10.02.1, nvCOMP 5.3.0.16, THP `madvise` (`raw/build-info.txt`) |
| Load-sensitive CTest dispositions | **none needed**: `not_passed` is empty in all three grade files, so no rerun was made |
| D11 case | **`with_d11`**: #228 is in F (merge `e3871ca2`). All six markers are present in all three grade files, and #228's tested source head `8cc1a377` is an ancestor of F |
| D10 outcome | **D10 resolved by fixing before freeze (#231, `55e30154`), and qualified on F: item 15 PASS.** F's EER decoder sources equal `97fb9fda`, so #231's 37-case damaged-input sanitizer matrix and 24/24 valid-input identity apply to F's decoder by citation (not rerun). Bounded result, not a claim about arbitrary damaged input (`docs/release/SUPPORT.md` §2) |
| Item 13 and `probe_item13_exit` | FAIL, dispositioned by hand (below) |

**Binary SHA-256 (frozen builds, Release `-O3 -DNDEBUG`):**

| Build | `motioncorr` | `motioncorr_faultinject` | `motioncorr_resident_retry_fault` |
|---|---|---|---|
| CPU | `43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42` | n/a | n/a |
| CUDA sm80 | `24a7bd26acbbf068aad6686971654941f0f648af52e8b60e52aa4550fd9fee9a` | `845ef3c9ece65742363c331b73f58ff9fdea52054d0a717ec7ecd86891630826` | `3f977ee8b1440b64478c4f6ac5702de81ce4fd0612a78f649432bc0822dfb98a` |
| CUDA sm80 + nvCOMP | `2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3` | `8a364eb329df9c04a3b802fa9381831ffa6911280b588c85a1221f87dae6cfcf` | `72588df8ec5ca225deb594e17fb76270c4d620d3fd6d9fb80c9e43e4ad203c83` |

Item 15's ASan build (`RelWithDebInfo`, ASan+UBSan) is `4bc1cc2d…a144` (`motioncorr`) and `1887af58…f62b`
(`runner_numerics`). Item 11's guard-removed control build is `ea95e866…7525`. Neither is a release binary.

## Per-item verdicts

| # | Item | Verdict | Result | Evidence |
|---|---|---|---|---|
| 0 | Source and builds | **PASS** | 3/3 rc 0, `-O3 -DNDEBUG` in `flags.make`, `CMAKE_HOME_DIRECTORY` = `$QF_W/src`; `ctest -N` 74/108/111 | `raw/logs/build.out`, `raw/logs/{configure,build}-*.log` |
| 1 | CTest, CPU | **PASS** | 74/74, 0 skipped; `validate_test_collection` PASS (`CUDA-only required tests: not required`); `test_ci_fail_closed.py -v` 8 tests OK; reference 74; `probe_grade_ctest.py` PROBE PASS (9/9; base `cb3699ac`, D11 checkout F) | `raw/ctest-cpu.*`, `raw/probe_grade_ctest.out` |
| 2 | CTest, CUDA | **PASS** | 108/108, 0 skipped; validator PASS with `CUDA_REQUIRED_TESTS`; lane GPU0 `GPU-eddb42fe…` pinned by UUID under the GPU0 lock | `raw/ctest-cuda.*` |
| 3 | CTest, CUDA + nvCOMP | **PASS** | 111/111, 0 skipped; `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures` and `CudaAdler32` pass | `raw/ctest-nvcomp.*` |
| 4 | F3/F3b truncation | **PASS** | `TruncatedMrcMovie` and `TruncatedGainDefect` pass in all three builds; the `…Cuda` variants pass in both CUDA builds | grade files, `named_tests` |
| 5 | Route/product campaign | **PASS** | 14/14 (7 families × G/L): auto/compact/float complete with their routes witnessed; compact refused only on 10028 (G and L) with nothing published; products identical to auto. CPU-vs-CUDA `--gate backend` recorded, **not graded** (Tier B) | `raw/summaries/campaign/`, `raw/logs/item5_campaign.out` |
| 6 | CPU identity vs Q1 `1db86902` | **PASS** | `ref_cpu_vs_cpu` products-only PASS 14/14; the strict all-files comparison also passes 14/14 (reference `dd86cd41…6b26439`, hash-checked) | `checks.ref_cpu_vs_cpu` in each campaign case |
| 7 | #178 CPU unweighted path | **PASS** | 6/6 cases (noDW G/L, evenodd G/L, evenodd 23-frame L, nodose G) identical to `d7171b81`; the injected recoverable `cudaMalloc` failure at ordinal 16 reaches the CPU line and is identical. The injected code is not a real out-of-memory condition | `raw/summaries/fallback178/` |
| 8 | Multi-GPU publication | **PASS** | 8 arms (G/L × w1/w2/w4, mixed w1/w2), every dataset contract PASS: workers on distinct sampled UUIDs, shards partition the input, joint STAR order, `logfile.pdf` 30 pages from real Ghostscript, no leftover process. All pairs identical (products-only and identity lib, including s0); positive control PASS, flipped-byte control FAIL. Window: all four GPU locks plus the bench lock, 0 compute processes, CPUs 96–111 | `raw/summaries/multigpu/`, `raw/logs/item8_*.out` |
| 9 | Adapted #123 matrix | **PASS** | 16/16 rows and 28/28 arms witnessed on the lane UUID only, gain-effect control `differs: true`, rc 0, on **both** CUDA executables; source F, 0 modified files | `raw/matrix-{nvcomp,cuda}.json` |
| 10 | `CpuDoseSymmetry` + `Base` | **PASS** | both pass in CPU, CUDA and CUDA+nvCOMP; `MOTIONCORR_CPU_DOSE_SYMMETRY=AUTO` selects `symmetric` (production path) in all three; g++ 13.3.0; flags `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, no `-march=native`/`-mfma` | `raw/logs/configure-*.log`, grade files |
| 11 | EER compact #208 replay | **PASS** | 41/41 recorded cases PASS, 0 UNRUN (o1n is N/A here and runs in the guard-removed control); negative controls 4/4 rejected; guard-removed control o1n and o5n PASS (compact ≠ float without the guard) | `raw/item11-eer/summary{,-noguard}.json` |
| 12 | Resident retry #207 | **PASS** | `PatchRetryState` and `CudaResidentRetryFailures` pass; single-GPU 4/4 (retried 41/30/9/25, remaining-owned 0); dataset (GPU0 + GPU2 `GPU-063e5232…`) PASS: d1/d2/dshim identical, dpoison and dpoison_both refuse as #207 | `raw/item12-retry/results/` |
| 13 | Raw integer MRC #204 harness | **FAIL** (dispositioned) | 14 runs graded. Every record matches #204 except one case, `m0_swapped_nx128_inherited` (2 problems); the 6 KNOWN-F4 records are as expected. Driver exit 1 | `raw/item13-mrc/grade.json` |
| 14 | macOS | not graded | builds and runs; not qualified; known CPU CTest differences (below) | `raw/item14-macos/` |
| 15 | EER memory safety (D10) | **PASS** | (a) `EerMemorySafety` passes in all three grade files; (b) `asan-eer.exit` 0: build rc 0, `-fsanitize=address,undefined` in `flags.make`, both executables linked to libasan and libubsan, `EerMemorySafety` 1/1 passed, default `QF_BENCH_LOCK` (no warning); (c) `decoder sources == 97fb9fda: yes` | `raw/asan-eer.*` |
| 16 | `addToCPlot2D` (D13) | **PASS** | `ReportPlotUndefinedAxis` collected and passing in all three builds | grade files |
| 17 | Stale CUDA error after OOM (D11) | **PASS** | `with_d11` in all three grade files; `CudaStaleErrorAfterOom` passes in CUDA and nvCOMP; `validator_enforcement`: CUDA detected from `CMakeCache.txt`, log line present, the collection without the test is rejected with exactly that test missing; CPU log says `not required` | `raw/ctest-*.grade.json` |

Probes: `probe_campaign_refusal`, `probe_matrix_fallback_witness`, `probe_item12_dataset_grader` and
`probe_multigpu_dryrun` all PROBE PASS. The item 8 `--dry-run` paths printed their plans (`raw/logs/`).
`probe_item13_exit` FAILs; see the disposition.

## Dispositions

**Item 13 (and `probe_item13_exit`): FAIL under the frozen criterion; operator disposition: expected
behaviour change, accepted (W-QF, 2026-10-19).**

- **Case:** `m0_swapped_nx128_inherited`, a big-endian mode-0 MRC with nx = 128. #204 recorded it as an
  expected failure: read little-endian, nx = 128 becomes `INT_MIN`, `abs(INT_MIN)` is negative, and the
  inherited test in `src/rwMRC.h` `parseMRCHeader` never detected the byte swap. #204's CUDA record was
  "PASS" in the sense "fails the same way on every route"; its CPU record was FAIL.
- **Cause:** #231 (D10, `55e30154`; commit `37297bef`) replaced `abs(mode|nx) > SWAPTRIG` with ordered
  comparisons (the F5 header fix). The swap is now detected and the movie is processed.
- **Observed on F:** every arm completes with rc 0, a completion STAR (`corrected_micrographs.star`,
  `movie.star`) and an MRC product: CPU, and CUDA `float`, `auto` and `compact` (routes witnessed float,
  compact, compact). The grader therefore reports CUDA PASS→FAIL and CPU FAIL→PASS.
- **Not recorded by the harness:** route identity for this case. The harness skips the identity comparison
  for expected-failure cases, and the products were cleaned up by the driver.
- **Supplementary run (not a QF item):** `drivers/supp_m0_nx128.py`, same lane and binaries, through
  `qf_lane_exec.sh`. The case was run big-endian and with the same pixels written little-endian, on CUDA
  `float`, `auto` and `compact` and on the CPU build. All 8 arms rc 0; CUDA products identical across the
  routes for both byte orders; big-endian products identical to little-endian on every arm, CPU included,
  so the swap decodes to the same pixels (`raw/supp-m0-nx128.json`, `ALL_HOLD`).
- **Everything else in item 13** matched #204, including both `errors` runs (26 + 26 PASS) and the six
  KNOWN-F4 `damaged` records (F4, D5, #214).
- `probe_item13_exit` fails only because its precondition, an unmodified driver exiting 0, no longer holds
  on F. Its flipped-verdict half still makes the driver exit nonzero.
- Neither the grader nor #204's recorded expectation was changed.

## Item 14: macOS (reported separately, not graded)

This Mac (Apple M4 Pro, macOS 26.7.1, arm64), AppleClang 21.0.0, CMake 4.4.4, Python 3.14.8 + NumPy 2.5.4
(temporary venv), checkout at F (clean), `-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`, `ctest -j1`.
Binary `3705e4f2…6ef0`.

**Builds and runs; not qualified; known CPU CTest differences.** 74 collected, 72 passed, 1 failed
(`SyntheticRegression`: libc `rand()` differs from glibc, #222), 1 skipped (`NativeMovieStaging`).
`MultiGpuScheduling` passes: #223 (`ecb7d7f7`) is in F. No new difference. AUTO selects the original
dose-weighting loop (AppleClang on arm64 is not the qualified toolchain), and both `CpuDoseSymmetry` tests
pass. Ghostscript is not installed on this Mac.

## Not part of QF

**Release-checklist read-back (§2b; not a QF item):** both CUDA builds report `motioncorr_core CUDA
architectures: 80`, and `cuobjdump --list-elf` lists four sm_80 cubins in each (`raw/cubin-readback.txt`,
read-only, after the run).


Reported separately, as the runbook lists: QM, Tier D science (#61, not run), timing (none run), genuine
device poisoning (#213) and the parked items. **Second venue:** SCARF CTest of F is in #234 (`gnx002`, one
A100-SXM4-40GB). All three configurations graded FAIL on `ProfilingKit` alone (network `TMPDIR`; the
evidence rerun passed), with counts 74/108/111 and `with_d11`. Test-robustness follow-up: #235. It is a
separate venue, not a QF item.

## Resources

- **Host:** 4GPUs, workspace `/mnt/clathrin/alex-motioncorr-rc0/W-QF`.
- **Lane:** GPU0 `GPU-eddb42fe…`, CPUs 96–103, GPU0 correctness lock per run, bench lock probed.
- **Multi-GPU window:** 01:10–01:15Z, all four correctness locks plus the bench lock, CPUs 96–111. Item 12's
  dataset used GPU0 and GPU2.
- **Occupancy:** no foreign compute process at the start or before the window.
- **Wall times:** phase A (builds, CTest, ASan) 23:31–00:09Z; phase B 00:10–01:10Z; phase C 01:10–01:15Z,
  on 2026-10-18/19. These are not timing results.
- **Scratch:** W-QF is 7.7 GB at the end, and the programme area is 88 GB of its 300 GB cap.
- **Drivers:** `raw/drivers/`, outside `tools/`, so the tools stay equal to F.
