# RC0 final qualification (QF): runbook

QF is the full CPU + native CUDA qualification of the exact RC0 composition (#198, register row QF). Its
suites are the Q1 suites ([PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209)) plus the
route/product campaign, the adapted #123 compact-ingest matrix and the items merged after Q1. This file says
what to run on the frozen SHA, where, and what counts as a result. The rehearsal of it on `483e881d` is in
[`rehearsal_483e881d/`](rehearsal_483e881d/README.md).

## Verdicts

Every item ends in exactly one of:

- **PASS**: the command ran to completion on the frozen SHA's binaries, in the stated lane, and every pass
  criterion below holds.
- **FAIL**: it ran, and a criterion does not hold. A FAIL is reported with its evidence; it is not re-run until
  green. A rerun is allowed only for a test already classified as load-sensitive (listed per item), and both
  results are reported.
- **UNRUN**: not run, run on a different SHA, run partially, or run without the lane/lock/witness conditions.
  UNRUN is never PASS and is listed in the QF report with the reason.

No gate, threshold or required-test list may be changed to obtain a PASS (`AGENTS.md`, `docs/gate_contract.md`).
Gate names below are from `docs/gate_contract.md`: **Tier A** (`--gate exact`, CPU regression), **Tier B**
(`--gate backend`, CPU-agreement diagnostic, never an acceptance result), **Tier C** (known-motion launcher),
and **same-backend identity** (repeat/route/batch/resume equality on one backend, the requirement listed in
the backend-profile section). Product identity is graded with `docs/issue85_laneC/compare_output_trees.py`
(MRC header + payload + STAR; `--products-only`) unless a row says otherwise.

## Lanes, locks and inputs

| | |
|---|---|
| Host | 4GPUs (`ssh 4GPUs`), 4x A100 80GB PCIe, driver 570.86.10, CUDA 12.8.61, g++ 13.3.0, nvCOMP 5.3.0.16 (`~/nvcomp53`), CMake 3.28.3, Python + NumPy in `~/.mc-venv`, Ghostscript 10.02.1 |
| Single-GPU lane | one GPU pinned **by UUID** (`CUDA_VISIBLE_DEVICES=GPU-…`; ordinals identify nothing), its 8 CPUs via `taskset`, the GPU's `/tmp/motioncorr-gpuN-correctness.lock` held per run. Rehearsal lane: GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, CPUs 96–103 |
| Multi-GPU lane | all four `gpuN-correctness` locks in ascending order, then `/tmp/motioncorr-bench.lock`; no foreign compute process on any GPU; 16 CPUs (two 8-CPU ranges) |
| Bench lock | before every build, CTest batch and GPU run: `flock -n /tmp/motioncorr-bench.lock true`; if held, poll every 60 s. Never touch the holder |
| Scratch | `/mnt/clathrin/alex-motioncorr-rc0/<worker>/` (`QF_W`), with `src/` a real git checkout of the frozen SHA (`CiFailClosedControls` needs `.git`) |
| Corpus | `~/motioncorr-validation-20261011-vm/{tutorial-data,corpus}`; EMPIAR-10164/10216 from Q1's verified re-fetch `/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data/`. Every movie and gain is hashed against `docs/workload_corpus/corpus.md` by `product_campaign.py` |
| #178 reference | Q1's retained `d7171b81` builds in `/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/` (`build-pre178-nvcomp`, `build-pre178-fi`) |

Tools are in [`tools/`](tools/). Copy them to `$QF_W/tools/` on the host and run them from `$QF_W`. Every tool
takes its workspace and lane from the environment and **stops with an error if a variable is unset**; no
tool has a built-in workspace, binary or lane:

```sh
export QF_W=/mnt/clathrin/alex-motioncorr-rc0/W-QF            # holds src/ (frozen checkout) and build-*/
export QF_SHA=<frozen sha>
export QF_CPUS=96-103 QF_GPU_UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 \
       QF_GPU_LOCK=/tmp/motioncorr-gpu0-correctness.lock
export QF_MG_CPU_A=96-103 QF_MG_CPU_B=104-111 QF_MG_W1_GPU=0  # multi-GPU window only
export QF_DATASET_GPU2_UUID=<second GPU UUID> QF_DATASET_CPUS2=104-111   # item 12 dataset part only
```

Historical reference binaries are named explicitly and hash-checked by the tools that use them: Q1's CPU
`1db86902` (`dd86cd41…6b26439`, `QF_REF_CPU_BIN`), Q1's CUDA+nvCOMP `1db86902` (`77db3f92…412a99`,
`QF_REF_CUDA_BIN`) and Q1's `d7171b81` #178 references. They are comparison arms only; every graded arm runs
the frozen binaries in `$QF_W/build-*`.

## Step 0: source and builds (owner: QF runner)

```sh
bash tools/build.sh     # checks HEAD == $QF_SHA and a clean tree, then CPU, CUDA sm80, CUDA sm80+nvCOMP; -j8 on $QF_CPUS
```

PASS: three `rc=0`, `-O3 -DNDEBUG` in `flags.make`, `CMAKE_HOME_DIRECTORY` = `$QF_W/src`, binary sha256
recorded. Wall ≈ 6 min (rehearsal: 1.2, 2.3 and 2.3 min).

## D4 freeze record (owner: QF runner; required before any item counts)

The QF report opens with: the frozen SHA (D4) and its `git rev-parse HEAD` in `$QF_W/src`; `git status
--porcelain` empty at build time and at the end of the run; the sha256 of every file in `$QF_W/tools/` (equal
to the committed `docs/rc0/qf/tools/` at a named commit); the sha256 of `motioncorr`,
`motioncorr_faultinject` and `motioncorr_resident_retry_fault` in each build; the GitHub Actions run on the
frozen SHA with its conclusion (Linux CTest + CUDA compile-only; compile-only CUDA is not native evidence);
host, driver and toolchain identity (`build-info.txt` as in the rehearsal); **which D11 case applies**: whether
#228 is in the frozen SHA (its merge commit, or "not merged at F"), as `d11.case` in the three
`ctest-<cfg>.grade.json` files (item 17); and **the D10 outcome** (item 15). A missing element makes every item
UNRUN.

## Items

| # | Item | Owner | Gate | Command (from `$QF_W`) | PASS criterion | Notes |
|---|---|---|---|---|---|---|
| 1 | CTest, CPU build | QF runner | Tier A (`SyntheticRegression`, `Runner*`) + unit/contract tests | `bash tools/run_ctest.sh cpu; python3 tools/grade_ctest.py cpu` | `ctest-cpu.grade.json` verdict PASS: `validate_test_collection` PASS, `test_ci_fail_closed.py -v` rc 0, the JUnit test set equals the `ctest --show-only` collection of the frozen build, every test passes (0 failed, skipped or not run), every name in the frozen `DEFAULT_REQUIRED_TESTS` is collected, every test named by items 4, 10, 12, 15 and 16 passes, and the count equals the reference for the D11 case (table below) | `ProfilingKit` is load-sensitive (30 s subprocess timeout, Q1); one rerun allowed (`run_ctest.sh cpu rerun '^ProfilingKit$'`, then `grade_ctest.py cpu --rerun-tag rerun`), both reported |
| 2 | CTest, CUDA build | QF runner | same + CUDA fault/fallback/staging tests | `bash tools/run_ctest.sh cuda; python3 tools/grade_ctest.py cuda` | as 1 (no `test_ci_fail_closed` step), plus `CUDA_REQUIRED_TESTS` when the frozen validator has it (item 17); lane GPU witnessed (UUID pin + lock) | `MultiGpuScheduling` has a known 0.25 s timing flake: one rerun allowed, as `ProfilingKit` |
| 3 | CTest, CUDA+nvCOMP build | QF runner | same + nvCOMP acceptance/reconstruction failures, Adler32 | `bash tools/run_ctest.sh nvcomp; python3 tools/grade_ctest.py nvcomp` | as 2, plus `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`, `CudaAdler32` pass | covers #217 (T3) boundary/decline tests natively |
| 4 | F3/F3b truncation (#205) | QF runner (inside 1–3) | failure/publication semantics | CTests `TruncatedMrcMovie`, `TruncatedGainDefect` (CPU) and `TruncatedMrcMovieCuda`, `TruncatedGainDefectCuda` (CUDA builds) | all four present in the collection (required list) and pass | no separate command |
| 5 | Route/product campaign | QF runner | same-backend identity (route invariance); Tier B diagnostic only | `taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/product_campaign.py` (all 7 families × G/L) | per case: `--ingest auto/compact/float` complete (or `compact` refused exactly where auto is float, i.e. 10028, and the refused arm publishes no corrected MRC, no per-movie STAR and no joint-STAR row for the movie); compact/float arms witness their route; products identical to auto; every GPU run witnessed on the lane UUID only; `verdict` PASS in 14/14 | CPU-vs-CUDA `--gate backend` is recorded, never graded (S1/D7). Strict all-files identity needs the declared route-log allowance; recorded, not a gate |
| 6 | CPU identity vs Q1 | QF runner | same-backend identity, CPU | item 5 with `QF_REF_CPU_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr` (sha256 `dd86cd41…6b26439`) | `ref_cpu_vs_cpu` products-only PASS on every case where the composition says valid-input bytes are unchanged | if a merged item intentionally changes CPU bytes (none known; #220's identity claim is 4/4), the case is reported as an expected difference with the PR reference |
| 7 | #178 CPU unweighted path (C1) | QF runner | same-backend identity vs pre-#178 | `python3 tools/fallback178.py` and `python3 tools/fallback178_injected.py` | 6/6 cases identical to `d7171b81`; the injected recoverable `cudaMalloc` failure reaches the CPU line and is identical | the register requires this frozen-SHA rerun |
| 8 | Multi-GPU publication 1/2/4 workers | QF runner | dataset endpoint contract + same-backend identity across worker counts | reserve the window: `multigpu_step.sh` takes all four `gpuN-correctness` locks (ascending) **and** the bench lock and waits until no compute process is on any GPU; then `bash tools/multigpu_step.sh --configs G,L` (s0, w1, w2, w4 per config) and `bash tools/multigpu_step.sh --mixed` (w1, w2) | per arm `dataset_status` PASS, aggregate PASS, workers on distinct witnessed UUIDs, shards partition the input, joint STAR order, `logfile.pdf` rendered by real Ghostscript, no leftover process; all arm pairs identical (products-only and identity lib); positive control PASS, flipped-byte control FAIL; all 8 arms (G/L × w1/w2/w4, mixed w1/w2) present | `python3 tools/multigpu_publication.py [--mixed] --dry-run` needs no locks and is side-effect free (`tools/probe_multigpu_dryrun.py`) |
| 9 | Adapted #123 compact-ingest matrix | QF runner | same-backend identity (u16 vs float32 TIFF twin, repeat, resume) | `QF_W=$QF_W flock $QF_GPU_LOCK taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/run_compact_ingest_support_matrix.py --binary build-<cfg>/motioncorr --device $QF_GPU_UUID --workdir matrix-<cfg> --json matrix-<cfg>.json` for `<cfg>` in `nvcomp`, `cuda` | 16/16 rows PASS, 28/28 arms UUID-witnessed, gain-effect control `differs: true`, rc 0; on **both** CUDA executables | adaptation record below; maintainer decision: run on the frozen executable, not merged into `tests/` |
| 10 | `CpuDoseSymmetry` + `CpuDoseSymmetryBase`, recorded toolchain (#220) | QF runner, after #220 merges | exact-bit CPU dose weights (test-internal oracle) | inside items 1–3; record the `MOTIONCORR_CPU_DOSE_SYMMETRY` selection each build reports, `g++ --version`, and the compile flags from `flags.make` (no `-march=native`/`-mfma` or other FMA flag) | both tests collected (required list) and pass in **every shipped configuration** (CPU, CUDA, CUDA+nvCOMP, and any other build offered for release); the reported AUTO path matches #220's qualified-toolchain contract (AUTO = x86-64 GCC without FMA; original loop elsewhere unless `ON`) | **N/A while #220 is unmerged; UNRUN if #220 is in the frozen SHA and this is not done.** Native-FMA flags are unqualified: QF must not recommend them |
| 11 | EER compact (#196): #208 matrix replay | QF runner | same-backend identity, refusal/overflow guards, D6 batch behaviour, against #208's record | `taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item11_eer.py --negative-controls`; then `bash tools/item11_noguard_control.sh` (powered control) | `summary.json`: every replayed case PASS, 0 UNRUN (`--skip-heavy` makes the up2-F4/up3 cases UNRUN), `negative_controls_all_rejected: true`; `summary-noguard.json`: o1n and o5n PASS (compact ≠ float without the guard). Per-case predicates are in the script header: rc, routes, recorded comparisons, UUID witness, no joint STAR after a nonzero exit, refusal with no publication, guard log line, and for b1–b6 the published set, every MRC payload hash, frame counts, D6 skip warnings, error messages and auto-vs-float identity as #208 | details below. D6/E-1 skip-and-warn is preserved behaviour; EER-MS (#221) is separate, see item 15 |
| 12 | Resident retry (#197): #207 success, recoverable, fatal, grouping, dataset | QF runner | same-backend identity + failure/publication, against #207's record | single GPU: `taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item12_retry.py`; dataset (multi-GPU window, two GPUs): `bash tools/multigpu_step.sh --driver item12_retry.py --dataset` | CTests `PatchRetryState`, `CudaResidentRetryFailures` pass (items 2–3) **and** every `item12-retry/results/*.json` verdict PASS: 4 single-GPU cases (retried 41/30/9/25, counter = retried, recoverable = one warning and identical products, fatal = refusal and no publication, remaining-owned 0) and `dataset.json` (d1/d2/dshim healthy and identical, dshim counter = retried; dpoison: #207's asymmetric case, worker rcs [0, 1] with the fault attributed to the second GPU's worker only, its earlier movie kept, the healthy worker complete, nothing merged; dpoison_both; every arm with status files, device witness and cleanup) | `probe_item12_dataset_grader.py` (a run that never exercised the fault, including rc 127 with no files, must FAIL) |
| 13 | Raw integer MRC staging (#195): #204 harness | QF runner | same-backend identity; F3 fail-closed; refusal routes | `bash tools/item13_mrc.sh` (writes `$QF_W/item13-mrc/`, ends with `grade_item13.py`; **its exit status is the grader's**) | driver exit 0 and `grade.json` verdict PASS: every record's verdict equals #204's, except both `errors` runs, where all 26+26 must now PASS (#205); the 6 F4 `damaged` records stay FAIL and are listed as KNOWN-F4 | `probe_item13_exit.sh` (one flipped verdict must make the driver fail). F4 is a documented RC0 limitation (D5, #214) |
| 14 | macOS | **macOS worker (not W-QF-PREP; assigned by the coordinator)** | none: not a qualification | `cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`; `ctest` | not graded. Reported as **"builds and runs; not qualified; known CPU CTest differences"**, with the actual failing tests listed | known differences: `SyntheticRegression` (libc `rand()` in hot-pixel replacement, #222) and `MultiGpuScheduling` (test-harness temp-path issue, fixed by PR #223). Record whether #223 is in the frozen SHA (it is **not** in `483e881d`; #223 is open). Reported separately from QF |
| 15 | EER memory safety (#231, D10; EER-MS #221) | QF runner | (a) damaged-EER failure/publication semantics on the release binaries; (b) ASan+UBSan on the frozen SHA; (c) #231's recorded evidence, cited | (a) inside items 1–3; (b) `bash tools/asan_eer.sh` (CPU only, no GPU; writes `asan-eer.{log,exit}`); (c) recorded by (b) | (a) `EerMemorySafety` passes in all three grade files; (b) `asan-eer.exit` 0: build rc 0, `-fsanitize=address,undefined` in `flags.make`, `motioncorr` and `runner_numerics` linked to libasan and libubsan, `EerMemorySafety` 1/1 passed (the test fails on any `AddressSanitizer`, `LeakSanitizer` or `runtime error:` line in a child log); (c) `asan-eer.log` says `decoder sources == 97fb9fda: yes` | **D10 was resolved by fixing before freeze: #231, merged at `55e30154`.** Why (b): #231's sanitizer runs were on its own branch (`97fb9fda`, `8932a83a`), never on the composition; (b) costs ≈ 5 min. Not re-run: #231's 37-case V-EER damaged-input matrix (6 arms, 0 sanitizer reports at the head, R-D10a) and its 24/24 valid-input identity; their harness is hard-wired to #231's workspace. (c) cites them for F only while F's EER decoder sources (`renderEER.cpp/.h`, `rwMRC.h`, `strings.cpp`) equal `97fb9fda`; if not, (c) is UNRUN and so is item 15. Items 1–3 and 11 unchanged. The QF report states the D10 outcome with item 15's verdict; if it is not PASS, the report says EER-MS is fixed in source but not qualified on F. D6 skip-and-warn (item 11) is separate |
| 16 | `addToCPlot2D` undefined x-axis (#230, D13; #229) | QF runner (inside 1–3) | report-plot regression | CTest `ReportPlotUndefinedAxis` | collected (required list) and passes in all three grade files | no separate command |
| 17 | Stale CUDA error after a handled OOM (#228, D11; #226 D1), **only if #228 is in the frozen SHA** | QF runner (inside 1–3, graded by `grade_ctest.py`) | failure semantics + fail-closed collection | none beyond items 1–3 | `d11.case` is the same in all three grade files. **`with_d11`** (F registers `CudaStaleErrorAfterOom` in `CMakeLists.txt`, has `tests/run_stale_cuda_error_controls.py` and lists the test in `CUDA_REQUIRED_TESTS`): the test passes, not skipped, in the CUDA and nvCOMP grade files; `d11.validator_enforcement` on both CUDA builds shows the frozen validator detects CUDA from the build's `CMakeCache.txt`, the run log says `CUDA-only required tests: required`, and the same collection without `CudaStaleErrorAfterOom` is rejected with exactly that test missing; the CPU log says `not required`; item 1's `test_ci_fail_closed.py` includes #228's case E. **`without_d11`** (none of the three): N/A, the test must not be collected, and the D4 record says #228 is not in F | mixed markers are a FAIL. #228's tested source head is `8cc1a377` (later commits on its branch change only `docs/rc0/stale_cuda_oom/`); the grade file records whether it is an ancestor of F. D11's D14 timing is #228's gate, not QF's |

**Expected CTest collections.** `grade_ctest.py` derives the expected set from the frozen build (`ctest
--show-only`) and the frozen required lists, and cross-checks the count against this table:

| Frozen SHA | CPU | CUDA | CUDA+nvCOMP |
|---|---|---|---|
| main `cb3699ac` (#231, #230), without #228 | 74 | 107 | 110 |
| main `cb3699ac` + #228 | 74 | 108 | 111 |

Measured at `cb3699ac` with `run_ctest.sh`: 74/74, 107/107, 110/110, `validate_test_collection` and
`test_ci_fail_closed` PASS. The with-#228 row is #228's composed result at `1afa03b5` (72/106/109) plus the
two tests #231 and #230 add to every configuration; it is not yet measured. A count matching neither row
means the frozen composition differs from this runbook: the grade is FAIL until the runbook is revised for it.

Reported separately from QF, not part of its acceptance: QM memory admission (separate worker), macOS (item
14), Tier D science (#61), SCARF second venue, timing/performance, genuine device poisoning (#213), parked
items (C6, C7/#219, E2/#211, T1/#206, L1).

## Release documentation hand-offs (owner: W-REL, #201; QF supplies the results)

QF does not edit release documents. At freeze, #201 must be finalised with completed versus pending
qualification distinguished, and must carry:

| Item | Content the docs must state |
|---|---|
| C3 | THP / `GLIBC_TUNABLES` deployment setting and allocator guidance (#188) |
| F2 | `tools/run_known_motion_gates.py` regenerates tracked fixtures by default: Tier C runs use `--fixtures <scratch>` (verified workaround). QF itself runs no Tier C launcher; Tier C is covered by the CTests that wrap it in items 1–3 |
| DOC1 / REL | inherited host-memory behaviours (`--grouping_for_ps` full host Fourier movie on the resident path, `_PS.mrc` left after a later failure, per-geometry VRAM floors), no-rollback failure semantics |
| F4 | compressed MRC decoder exit status is not checked; validate inputs independently (`xz -t`, `zstd -t`, `bzip2 -t`) before processing (#214) |
| D6 / E-1 | EER damaged fractions are skipped with a warning; truncated EER without `--expected_frames` is processed as a shorter movie |
| D10 / EER-MS | D10 = fix before freeze, done by #231 (`55e30154`): host EER decoding is bounded by each fraction's length (over-reading fractions take the D6 skip-and-warn path), container damage (strip size or range, failed directory or strip reads, missing tags) fails that movie instead of the process, and malformed MRC header dimensions are rejected. Valid input decodes bit-identically (#231). The qualification status is item 15's verdict; the docs must not call the EER input paths qualified unless item 15 is PASS |
| D11 | whether #228 is in RC0 (D4 record). If not, the known defect: after a handled CUDA allocation failure, a stale last error can degrade or refuse the next movie (#226 D1) |
| S1 / D7 | the CUDA local-alignment statement (evaluation RC0) |
| QM, macOS | their separate status |

## Items 11–13: how the harnesses were ported

The #204/#207/#208 scripts referenced their own scratch trees, lanes (GPU2/GPU3) and historical binaries. QF
does not invoke them in place:

- **Item 13 (#204):** `harness_mrc/synth_mrc_matrix.py` and `real_data_identity.py` are #204's files with one
  change (source root = `$QF_W/src`, required). They already take `--binary`; QF passes `qf_lane_exec.sh`,
  which runs `$MC_BIN` (a frozen build) under the lane lock, bench probe, UUID pin and CPU mask, and logs the
  binary hash of every invocation. The run list mirrors #204's (CUDA sections, CPU matrix and errors, real
  data G/L, the six option sets of #204's `run_options.sh`). Real-data inputs are checked against #204's
  recorded hashes. `grade_item13.py` compares per-record verdicts with `item_records/mrc_204.json` (extracted
  from #204's JSONs). Self-test on #204's own JSONs: 40 mismatches (exactly the pre-#205 error records), and
  PASS once those records pass.
- **Item 12 (#207):** #207's shell scripts are not reused. `item12_retry.py` re-implements their runs (the same
  inputs, hash-checked against #207's list; the same options; #207's retry accounting, log allowances and
  dataset comparison rules) against the frozen `motioncorr` and `motioncorr_resident_retry_fault`, with Q1's
  CUDA `1db86902` as the reference arm (#207's "db"). Not ported: #207's pre-#197 and reverse-applied builds
  and its mutants (they established the comparison's power at `1db86902`). #210 removed the shim's
  `MC_FAULT_ONLY_CVD`. #207's asymmetric poison case is restored by `qf_fault_by_uuid.sh`, a hashed wrapper
  passed as the launcher's `--binary`: it enables the fatal fault only when the worker's
  `CUDA_VISIBLE_DEVICES` is the chosen UUID, logs `fault=on`/`fault=off`, and execs the unchanged frozen shim.
  The both-workers case is kept as an additional check. `grade_dataset()` reads every verdict from the run's
  own files; a missing file is a failure.
- **Item 11 (#208):** `item11_eer.py` replays every case in `item_records/eer_208.json` (extracted from #208's
  case and result files and `batch_analysis.json`) with the recorded options and arms on the frozen binaries,
  and grades #208's per-movie predicates before deleting products (script header). The batches are healthy A
  (Falcon3 movie 1), a damaged copy of A, and healthy B (Falcon3 movie 2), as #208. The damaged movies are
  regenerated with #208's `eer_corrupt.py` and must equal #208's hashes. #208 did not record its
  `eer_synth.py` parameters, so the synthetic movies follow a **frozen replacement recipe**: generator
  (`harness_eer/eer_synth.py`, #208's), seed and parameters in `SYNTH`, with expected hashes in
  `item_records/eer_synth_recipe.json`. Every run regenerates them and stops on any mismatch. The recipe file
  also records, from an independent decode of each fixture's strips, its encoding (65000/65001/65002),
  detector (4K/2K), fraction count (240/49 152/196 608) and the largest per-pixel count of one group at each
  overflow case's grouping and upsampling: o2 65 532, o3 65 535, o1/o4/o5 65 536, the same boundaries as
  #208 section 4. #208's historical fixture hashes are not these bytes. `item11_noguard_control.sh` repeats
  #208's guard-removed control (o1n) and adds o5n on the replacement fixtures, so the overflow cases are
  shown to reach the wrap.

## Adapted #123 matrix: what changed

Source: #123 `t3code/compact-ingest-compatibility-tests` @ `cfa331eb`. Files in [`tools/`](tools/):

| File | Relation to `cfa331eb` |
|---|---|
| `compact_compare_output_trees.py` | `docs/issue85_laneC/compare_output_trees.py` **byte-identical** (sha256 `b5d5d998…41732`, the comparator of #123's runs of record). Main's copy lacks the schema-2 contract (per-movie product sets, per-product geometry, `general_tags`, `joint_tag`, `forbidden_joint_tags`) the matrix grades with |
| `compact_ingest_fixtures.py` | `tests/compact_ingest_fixtures.py` with one change: the TIFF writer is inlined verbatim from `cfa331eb:tests/test_tiff_read.py`, because main's `write_tiff` no longer takes `sample_format` |
| `run_compact_ingest_support_matrix.py` | `tests/run_compact_ingest_support_matrix.py` with adaptations A1–A5, each marked `QF adaptation` in the source |

- **A1, comparator path:** loads the vendored comparator beside it.
- **A2, host-fallback rejection (added; revision 1):** the original rejections of
  `Materialized native uint16 frames as float for CPU fallback.` and `No resident CUDA session; widening the
  native uint16 movie to float.` are kept. Main no longer prints the second (the compact route is chosen only
  with a live session, `motioncorr_runner.cpp` 2363/2383), and it prints `Materialized native <type> …` for
  every staged type, so any `Materialized native ` line is also rejected. (The first port replaced the
  NO_SESSION check with the prefix check; R-QF showed a synthetic log with the old literal then passed.
  `tools/probe_matrix_fallback_witness.py` now shows all three fallback logs rejected and the clean log accepted.)
- **A3, route witness (added):** every arm passes `--ingest_witness`. Each eligible movie must record
  `compact` and each ineligible movie `float` (never `nvcomp`; the fixtures use whole-frame strips, which
  nvCOMP declines).
- **A4, fixture identity (added):** every generated movie, damaged movie and gain must equal #123's recorded
  SHA-256 (7 distinct files). They do, so the inputs are the bytes #123 graded.
- **A5, provenance (added):** the JSON records the source commit, modified-file count and the original harness,
  comparator and fixture hashes.

Unchanged, so no #123 assertion is removed: the 16 rows, the options, every witness literal (`Staging this movie as native
unsigned 16-bit`, `Released native uint16 host staging after device forward FFT.`, `Movie FFT: batch=1`,
`Reconstruction Profile (Resident VRAM)]`), the compute-apps UUID join, the per-arm manifest validation, the
non-constant-product check, the float-twin, repeat and resume comparisons, the powered resume control, the
failing-movie checks and the cross-case gain-effect control. Main's CLI accepts every option the matrix passes
(`--max_io_threads`, `--angpix`, `--voltage`, `--ps_size`, …), and early binning still has no resident
session, so the `ineligible_early_binning` row tests the same predicate.

## Estimated QF wall-clock (frozen SHA)

From the rehearsal ([details](rehearsal_483e881d/README.md#estimated-qf-wall-clock-on-the-frozen-sha)), measured:
builds + three CTest configurations 26 min, #123 matrix 1 min, item 11 ≈ 31 min (with negative and guard-removed
controls), item 12 ≈ 7 min, item 13 5.4 min. Since the rehearsal each configuration gained 6 tests (68/101/104 to
74/107/110), mainly `EerMemorySafety` at 22–28 s per configuration, so builds + CTest ≈ 28 min run one after
another (the `cb3699ac` CTest times, 6.0/9.2/9.2 min, were three configurations at once on separate lanes and are
not sequential times); `CudaStaleErrorAfterOom` adds 1–3 s per CUDA build. Estimated: item 15's ASan build and
test ≈ 5 min, campaign 15–25 min, #178 ≤ 30 min, multi-GPU 30–45 min once all locks are free. Total ≈ 2.5–3 h,
excluding lock waits and macOS.
