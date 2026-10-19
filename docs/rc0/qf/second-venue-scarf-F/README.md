# Second venue: native CTest of F on SCARF

Reported separately from QF ([runbook](../README.md), "Reported separately"). This is not a QF item and not a tag
gate. Refs #198.

## Result

`grade_ctest.py` grades all three configurations **FAIL**, and in each one the only failure is `ProfilingKit`.
The collected counts match the runbook's `with_d11` row (74/108/111), `d11.case` is `with_d11` everywhere, and
every other test passes, including every test the runbook names for items 4, 10, 12, 15, 16 and 17.

The `ProfilingKit` failures are 6 `OSError: [Errno 39] Directory not empty` errors in `tempfile` cleanup
(`tearDown`) in each configuration. They happened because the SCARF login profile exports
`TMPDIR=/scratch/scarf1415/relion-container-tests/tmp`, a PanFS path, and the job inherited it. The runbook allows
one rerun for evidence. That rerun used `run_ctest.sh <cfg> rerun '^ProfilingKit$'` with `TMPDIR` on node-local XFS
(`/tmp`); nothing else changed. It passed in all three configurations (exit 0), so the cause is the temporary
directory being on PanFS, not the test itself. As the runbook requires, the verdict stays FAIL. The rerun is
recorded under `rerun_info_not_graded` in each `ctest-<cfg>.grade.json`.

| Config | `motioncorr` sha256 | Collected / reference | Passed | `d11.case` | Verdict | Not passed | Rerun (`TMPDIR=/tmp`) |
|---|---|---|---|---|---|---|---|
| CPU | `6cf4c43d29fb501a07c150d035a64be235ad3b2152be79851a946d529bfeb7a3` | 74 / 74 | 73 | `with_d11` | FAIL | `ProfilingKit` | passed, exit 0 |
| CUDA sm80 | `4e280b1e2c049ff991a05fdecab7492f018aa96049ec50c8eaf0bde11c3f68a5` | 108 / 108 | 107 | `with_d11` | FAIL | `ProfilingKit` | passed, exit 0 |
| CUDA sm80 + nvCOMP | `682cfc88c380283203b5064ac13021672ad94a63f20516fe4afe65bc07d16ce5` | 111 / 111 | 110 | `with_d11` | FAIL | `ProfilingKit` | passed, exit 0 |

Other checks that hold in every configuration:
- `validate_test_collection` PASS with rc 0. On the CPU build, `test_ci_fail_closed.py -v` returned rc 0.
- No test was skipped or not run.
- The CUDA builds log `CUDA-only required tests: required` and the CPU build logs `not required`.
- On both CUDA builds, D11 validator enforcement holds: the full collection passes, and the same collection
  without `CudaStaleErrorAfterOom` is rejected with exactly that test missing.
- `8cc1a377` is an ancestor of F.

The main-run grades are kept as `ctest-<cfg>.grade.main.json`. They are identical to the final grades except that
the final grades include the rerun information.

## Source and tools

- `git clone` of `KingAlejandro/MotionCorr-standalone` on SCARF, then `git checkout --detach 6d68e2d6ec45c37b75fd0f4aaff8272f192b7029`.
  HEAD = F, `git status --porcelain` empty and no `._*` files at build time; HEAD and the clean tree were checked
  again at the end of the main run and of the rerun.
- The QF tools are F's `docs/rc0/qf/tools/`, copied from the checkout. Their sha256 values, in `raw/tools.sha256`,
  equal the committed files. `run_ctest.sh` and `grade_ctest.py` ran unmodified. Lane settings came only from
  their environment variables: `QF_W`, `QF_SHA`, `QF_CPUS` (the job step's `Cpus_allowed_list`), `QF_GPU_UUID`
  (the one GPU visible in the job) and `QF_GPU_LOCK` (a node-local file); see `raw/tools/env.sh`.
  `run_ctest.sh` replaces `LD_LIBRARY_PATH`. That does no harm here because every binary carries an RPATH to the
  CUDA and nvCOMP libraries; `raw/build-record.txt` shows `ldd` with `LD_LIBRARY_PATH` unset and nothing missing.
- Builds: `raw/tools/build_scarf.sh` is F's `build.sh` with three host paths substituted (venv, CUDA 12.8.0,
  nvCOMP). The flags are unchanged: `-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`,
  `-DCMAKE_CUDA_ARCHITECTURES=80`, and `-DUSE_NVCOMP=OFF/ON`. All three configure and build steps returned rc 0
  (`raw/logs/build.out`). `flags.make` gives `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`, with no FMA or
  `-march` flag. For CUDA it gives `-O3 -DNDEBUG -std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80]`.
  `CMAKE_HOME_DIRECTORY` is the checkout. Configure reports
  `CPU dose weighting: symmetric rows (AUTO: qualified x86-64 GCC without FMA)`, and `CpuDoseSymmetry` and
  `CpuDoseSymmetryBase` pass in all three configurations.

| Binary | CUDA | CUDA + nvCOMP |
|---|---|---|
| `motioncorr_faultinject` | `e65086d70c5bcf052b7cea2e05860881d4ac01a9d12c0832aa4447799432e94b` | `9dd9a7d651575cb392117ad76c4b5454330c0e3edda7281eef7977cfc7d24da6` |
| `motioncorr_resident_retry_fault` | `bb144e4532df4212e8b513411743601d6c0313fd7c42cc2652877fe2e1093e9f` | `d17a9c0c36fcd564d3371518729fd3ce8d36405471018b97e6381e2fbd12ae89` |

## Hardware and environment

| | SCARF (this run) | 4GPUs (runbook) |
|---|---|---|
| Node | `gnx002`, Slurm job 3636957 (`gpu-devel`, `--gres=gpu:1 --cpus-per-task=8 --mem=64G`) | 4-gpu-vm |
| GPU | 1 × NVIDIA A100-SXM4-40GB, `GPU-d4169778-fe7f-06ef-3807-b9e301b3b459`, the only device in the job's cgroup; no compute apps before or after | A100 80GB PCIe, pinned by UUID |
| Driver | 580.178.04 (driver CUDA 13.0) | 570.86.10 |
| CPUs | AMD EPYC 7252, mask `12-15,28-31` (4 cores + SMT siblings) | CPUs 96–103 |
| OS / kernel | Rocky Linux 9.8, 5.14.0-687.53.1.el9_8 | Ubuntu 24.04 |
| Compiler | g++ 11.5.0 | g++ 13.3.0 |
| CUDA toolkit | 12.8 V12.8.61 (EasyBuild `CUDA/12.8.0`) | 12.8.61 |
| nvCOMP | 5.3.0.16 | 5.3.0.16 |
| CMake | 3.31.8 | 3.28.3 |
| Python / NumPy | 3.12.3 (uv standalone build) / 2.5.3; no Pillow | 3.12.3 / 2.5.3 |
| Ghostscript, decoders | gs 9.54.0; pbzip2, zstd and xz present | gs 10.02.1 |
| THP | `always` | `madvise` |
| Exclusion | the Slurm allocation (cgroup GPU isolation); the `QF_GPU_LOCK` and bench lock files are node-local and had no other users | per-GPU and bench `flock` |

Full records: `raw/identity-build.txt`, `raw/identity-ctest.txt` and `raw/build-record.txt`.

## Differences from 4GPUs, and limitations

- **`TMPDIR` on PanFS** caused the only failures (above). `run_ctest.sh` does not set `TMPDIR`, so the suites
  inherit it from the caller's environment. Any SCARF run that inherits this login profile is expected to fail
  `ProfilingKit` the same way.
- **Pillow is absent.** `TruncatedGainDefect` skips its EER gain section internally without Pillow and still
  passes. CTest prints output only on failure, so the logs cannot show whether that section ran. Whether the 4GPUs
  venv has Pillow was not checked; this run did not touch 4GPUs.
- **GPU visibility in the CPU suite.** `run_ctest.sh` leaves `CUDA_VISIBLE_DEVICES` unchanged for the CPU
  configuration, so the CPU log header reads `gpu: 0` (Slurm's value) rather than `none`. The CPU build has no
  CUDA.
- 40 GB SXM4 GPU, a newer driver branch, and an older g++ and Ghostscript than 4GPUs. These are the points of the
  second venue; no test reported a difference attributable to them.
- **No timing.** THP is `always`, and test durations in the logs are not comparable with 4GPUs.

**UNRUN at this venue** (outside this task's scope): every QF item other than the CTest suites. That covers items 5–9
and 11–13, item 15(b) `asan_eer.sh`, item 8's multi-GPU publication (only one GPU was allocated), and
`probe_grade_ctest.py`. Items 4, 10, 15(a), 16 and 17 ran only as the tests inside the three CTest suites.

## Files

`raw/` holds the run logs, JUnit XML, `.exit` files and grade files (`ctest-<cfg>*`), the main-run and rerun
summaries (`ctest-chain.out`, `ctest-rerun-chain.out`), the configure and build logs (`logs/`), `flags.make`, the
identity and build records, the Slurm allocation log, and the SCARF wrapper scripts (`raw/tools/`). Build trees on
SCARF were deleted after the copy.
