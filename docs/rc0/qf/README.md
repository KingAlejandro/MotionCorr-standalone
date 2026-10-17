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

Tools are in [`tools/`](tools/). Copy them to `$QF_W/tools/` on the host. The lane comes from the environment
(defaults are the rehearsal lane):

```sh
export QF_W=/mnt/clathrin/alex-motioncorr-rc0/W-QF            # holds src/, build-*/
export QF_CPUS=96-103 QF_GPU_UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 \
       QF_GPU_LOCK=/tmp/motioncorr-gpu0-correctness.lock
export QF_MG_CPU_A=96-103 QF_MG_CPU_B=104-111 QF_MG_W1_GPU=0  # multi-GPU only
```

## Step 0: source and builds (owner: QF runner)

```sh
git -C $QF_W/src rev-parse HEAD        # must equal the frozen SHA; git status --porcelain empty
QF_SHA=<frozen sha> bash tools/build.sh     # CPU, CUDA sm80, CUDA sm80+nvCOMP; Release; -j8 on $QF_CPUS
```

PASS: three `rc=0`, `-O3 -DNDEBUG` in `flags.make`, `CMAKE_HOME_DIRECTORY` = `$QF_W/src`, binary sha256
recorded. Wall ≈ 6 min (rehearsal: 1.2, 2.3 and 2.3 min).

## Items

| # | Item | Owner | Gate | Command (from `$QF_W`) | PASS criterion | Notes |
|---|---|---|---|---|---|---|
| 1 | CTest, CPU build | QF runner | Tier A (`SyntheticRegression`, `Runner*`) + unit/contract tests | `bash tools/run_ctest.sh cpu` | `validate_test_collection` PASS, `test_ci_fail_closed.py -v` rc 0, every collected test passes, 0 skipped | `ProfilingKit` is load-sensitive (30 s subprocess timeout, Q1); one rerun allowed, both reported |
| 2 | CTest, CUDA build | QF runner | same + CUDA fault/fallback/staging tests | `bash tools/run_ctest.sh cuda` | as 1; lane GPU witnessed (UUID pin + lock) | `MultiGpuScheduling` has a known 0.25 s timing flake: one rerun allowed |
| 3 | CTest, CUDA+nvCOMP build | QF runner | same + nvCOMP acceptance/reconstruction failures, Adler32 | `bash tools/run_ctest.sh nvcomp` | as 2 | covers #217 (T3) boundary/decline tests natively |
| 4 | F3/F3b truncation (#205) | QF runner (inside 1–3) | failure/publication semantics | CTests `TruncatedMrcMovie`, `TruncatedGainDefect` (CPU) and `TruncatedMrcMovieCuda`, `TruncatedGainDefectCuda` (CUDA builds) | all four present in the collection (required list) and pass | no separate command |
| 5 | Route/product campaign | QF runner | same-backend identity (route invariance); Tier B diagnostic only | `taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/product_campaign.py` (all 7 families × G/L) | per case: `--ingest auto/compact/float` complete (or `compact` refused exactly where auto is float, i.e. 10028); compact/float arms witness their route; products identical to auto; every GPU run witnessed on the lane UUID only; `verdict` PASS in 14/14 | CPU-vs-CUDA `--gate backend` is recorded, never graded (S1/D7). Strict all-files identity needs the declared route-log allowance; recorded, not a gate |
| 6 | CPU identity vs Q1 | QF runner | same-backend identity, CPU | item 5 with `QF_REF_CPU_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/build-cpu/motioncorr` (sha256 `dd86cd41…6b26439`) | `ref_cpu_vs_cpu` products-only PASS on every case where the composition says valid-input bytes are unchanged | if a merged item intentionally changes CPU bytes (none known; #220's identity claim is 4/4), the case is reported as an expected difference with the PR reference |
| 7 | #178 CPU unweighted path (C1) | QF runner | same-backend identity vs pre-#178 | `python3 tools/fallback178.py` and `python3 tools/fallback178_injected.py` | 6/6 cases identical to `d7171b81`; the injected recoverable `cudaMalloc` failure reaches the CPU line and is identical | the register requires this frozen-SHA rerun |
| 8 | Multi-GPU publication 1/2/4 workers | QF runner | dataset endpoint contract + same-backend identity across worker counts | `bash tools/multigpu_step.sh --configs G,L` then `bash tools/multigpu_step.sh --mixed` | per arm `dataset_status` PASS, aggregate PASS, workers on distinct witnessed UUIDs, shards partition the input, joint STAR order, `logfile.pdf` rendered by real Ghostscript, no leftover process; all arm pairs identical (products-only and identity lib); positive control PASS, flipped-byte control FAIL | needs the multi-GPU lane (all locks). `--dry-run` prints the commands without locks |
| 9 | Adapted #123 compact-ingest matrix | QF runner | same-backend identity (u16 vs float32 TIFF twin, repeat, resume) | `QF_W=$QF_W flock $QF_GPU_LOCK taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/run_compact_ingest_support_matrix.py --binary build-<cfg>/motioncorr --device $QF_GPU_UUID --workdir matrix-<cfg> --json matrix-<cfg>.json` for `<cfg>` in `nvcomp`, `cuda` | 16/16 rows PASS, 28/28 arms UUID-witnessed, gain-effect control `differs: true`, rc 0; on **both** CUDA executables | adaptation record below; maintainer decision: run on the frozen executable, not merged into `tests/` |
| 10 | `CpuDoseSymmetry` + base-path variant, recorded toolchain (#220) | QF runner, after #220 merges | exact-bit CPU dose weights (test-internal oracle) | inside items 1–3; plus record `MOTIONCORR_CPU_DOSE_SYMMETRY` selection from the binary's log/test output and `g++ --version`, `-march`/FMA flags from `flags.make` | `CpuDoseSymmetry` and its base-path variant collected (required list) and pass in every configuration; the AUTO selection printed for the QF toolchain matches #220's qualified-toolchain contract (AUTO enables only on x86-64 GCC without FMA) | **UNRUN until #220 merges**; if #220 is not in the frozen SHA this item is N/A and says so |
| 11 | EER compact (#196) | QF runner (W-EER-Q harness) | same-backend identity + refusal/overflow guards | item 5 (e12963, e10474f3 compact) and item 8 `--mixed`; full matrix: `docs/rc0/qual_eer_compact/eer_matrix.py` at [PR #208](https://github.com/KingAlejandro/MotionCorr-standalone/pull/208) `a5fa5429`, run against the frozen binaries | campaign/mixed rows PASS; matrix rows match #208's recorded verdicts (grouping/remainder, upsampling 1/2/−1, overflow guard, gain, pinned refusal) | D6/E-1 skip-and-warn and EER-MS (#221) are documented limitations, not QF FAILs; if a #221 fix lands, its own gates are added here |
| 12 | Resident retry (#197) | QF runner (W-RETRY-Q harness) | same-backend identity + failure/publication | CTests `PatchRetryState`, `CudaResidentRetryFailures`; item 8 `--mixed` (10641 retries 50/50 patches); full: `docs/rc0/qual_resident_retry/scripts/` at [PR #207](https://github.com/KingAlejandro/MotionCorr-standalone/pull/207) `9bb6ca5c` | CTests pass; mixed dataset identical across worker counts with no `resident retry preparation did not complete` warning | |
| 13 | Raw integer MRC staging (#195) | QF runner (W-MRC-Q harness) | same-backend identity; F3 fail-closed | CTests `SignedMrcStaging`, `NativeMovieStaging`; item 5 (e10216 int16, e10164 int8); `docs/rc0/qual_mrc_staging/synth_mrc_matrix.py` at [PR #204](https://github.com/KingAlejandro/MotionCorr-standalone/pull/204) `5944617b` | CTests pass; campaign rows PASS; error-route matrix now publishes **0/26** truncation variants (was 20/26 before #205) | F4 (compressed decoder exit status) is a documented limitation |
| 14 | macOS CPU build + CTest | **macOS worker (not W-QF-PREP; assigned by the coordinator)** | Tier A + contract tests | `cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`, `ctest` | as item 1 | `SyntheticRegression` and `MultiGpuScheduling` failed on macOS on every recent head (inherited, undiagnosed, #201/#217 evidence): until diagnosed they are FAIL, reported as known, not PASS |

Items not in QF (owned elsewhere): Tier D science (#61), SCARF second venue, timing/performance, QM memory
admission, genuine device poisoning (#213).

## Adapted #123 matrix: what changed

Source: #123 `t3code/compact-ingest-compatibility-tests` @ `cfa331eb`. Files in [`tools/`](tools/):

| File | Relation to `cfa331eb` |
|---|---|
| `compact_compare_output_trees.py` | `docs/issue85_laneC/compare_output_trees.py` **byte-identical** (sha256 `b5d5d998…41732`, the comparator of #123's runs of record). Main's copy lacks the schema-2 contract (per-movie product sets, per-product geometry, `general_tags`, `joint_tag`, `forbidden_joint_tags`) the matrix grades with |
| `compact_ingest_fixtures.py` | `tests/compact_ingest_fixtures.py` with one change: the TIFF writer is inlined verbatim from `cfa331eb:tests/test_tiff_read.py`, because main's `write_tiff` no longer takes `sample_format` |
| `run_compact_ingest_support_matrix.py` | `tests/run_compact_ingest_support_matrix.py` with adaptations A1–A5, each marked `QF adaptation` in the source |

- **A1, comparator path:** loads the vendored comparator beside it.
- **A2, host-fallback literal:** `No resident CUDA session; widening the native uint16 movie to float.` no
  longer exists on main. The compact route is now chosen only with a live session (`motioncorr_runner.cpp`
  2363/2383), so that fallback cannot occur. The check now rejects any `Materialized native ` line, which
  includes the original uint16 literal and every other staged type.
- **A3, route witness (added):** every arm passes `--ingest_witness`. Each eligible movie must record
  `compact` and each ineligible movie `float` (never `nvcomp`; the fixtures use whole-frame strips, which
  nvCOMP declines).
- **A4, fixture identity (added):** every generated movie, damaged movie and gain must equal #123's recorded
  SHA-256 (7 distinct files). They do, so the inputs are the bytes #123 graded.
- **A5, provenance (added):** the JSON records the source commit, modified-file count and the original harness,
  comparator and fixture hashes.

Unchanged: the 16 rows, the options, all witness literals that still exist (`Staging this movie as native
unsigned 16-bit`, `Released native uint16 host staging after device forward FFT.`, `Movie FFT: batch=1`,
`Reconstruction Profile (Resident VRAM)]`), the compute-apps UUID join, the per-arm manifest validation, the
non-constant-product check, the float-twin, repeat and resume comparisons, the powered resume control, the
failing-movie checks and the cross-case gain-effect control. Main's CLI accepts every option the matrix passes
(`--max_io_threads`, `--angpix`, `--voltage`, `--ps_size`, …), and early binning still has no resident
session, so the `ineligible_early_binning` row tests the same predicate.

## Estimated QF wall-clock (frozen SHA)

From the rehearsal ([details](rehearsal_483e881d/README.md#estimated-qf-wall-clock-on-the-frozen-sha)): builds + three
CTest configurations 26 min (measured), campaign 15–25 min, #123 matrix 1 min (measured), #178 ≤ 30 min,
multi-GPU 30–45 min once all locks are free, item harnesses 11–13 1–3 h. Core QF (items 0–10) ≈ 2–2.5 h; with
11–13 ≈ 3.5–5.5 h, excluding lock waits and macOS.
