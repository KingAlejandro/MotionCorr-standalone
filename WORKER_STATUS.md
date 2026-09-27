# WORKER_STATUS — issue #72

| field | value |
| --- | --- |
| issue | #72 — Fail-closed CI and canonical fixtures |
| model | `gemini-3.8-flash-high` via Antigravity (`antigravity`, displayed Alexgravity) |
| task class | validation |
| phase | 5/5 — Completed, validated on cpu64, committed & pushed |
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| head | `fc35be3e94ae90eb8095d911d19fce3dd06064e4` |
| branch | `round96/72-gemini-3-8-flash` |
| worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-1d15fa94` |
| PR | draft PR targeting `main` |

## Declared changed-file whitelist

This task does **not** modify the production pipeline or GPU kernels. It addresses CI failure-policy gaps, CMake test dependency enforcement, fixture integrity verification, and negative controls.

| path | status | kind | scope / role |
| --- | --- | --- | --- |
| `agents/designs/issue_72_fail_closed_ci_canonical_fixtures.md` | new | ADR | Architectural design record |
| `WORKER_STATUS.md` | new | handoff | Round 96 status handoff |
| `.github/workflows/ci.yml` | edit | CI | Remove silent truth-script skip, add fixture verification preflight, enforce CTest JSON collection validation |
| `CMakeLists.txt` | edit | build | Enforce Python3 and numpy when `BUILD_TESTING=ON` (leave `BUILD_TESTING=OFF` independent), additive test registration |
| `test-data/generate_known_motion_fixture.py` | edit | fixture | Guard manifest rewrite behind `--write-manifest` to prevent self-verifying noncanonical fixture overwrites |
| `tools/verify_fixtures.py` | new | tool | Fixture integrity checker against committed trusted git manifest |
| `tools/validate_test_collection.py` | new | tool | CTest suite collection validator using `ctest --show-only=json-v1` |
| `tools/test_ci_fail_closed.py` | new | test | 6 hermetic negative controls (absent truth script, absent dependency, empty test collection, missing fixture, byte-flipped fixture, noncanonical regenerated fixture) |

Explicitly **not** touched: `src/**`, `src/acc/cuda/*`, reference output data, numerical thresholds or tolerances, Actions permissions.

## Tests & Validation

All tests executed and verified on both local macOS (arm64) and remote Linux (`cpu64` / `small-refmac-machine`, x86_64, Ubuntu 24.04, node 1 / cores 32-47, under `flock /tmp/motioncorr-issue96-cpu-validation.lock`):

| command / suite | host | cores / node | result | notes |
| --- | --- | --- | --- | --- |
| `python3 tools/validate_test_collection.py --test-dir build` | local & cpu64 | cores 32-47 | PASS | Enforces collection >= 13, all required test targets present |
| `ctest --test-dir build --output-on-failure` | cpu64 | cores 32-47 (j8) | 14/14 PASS (100%) | Includes bit-for-bit exact `SyntheticRegression` (0.00 max px diff, 0.00 RMSE) |
| `python3 tools/verify_fixtures.py --fixtures-dir test-data/known_motion` | local & cpu64 | cores 32-47 | PASS | Compares all fixtures against canonical `git:HEAD:test-data/known_motion/MANIFEST.json` |
| `python3 tools/test_ci_fail_closed.py -v` | local & cpu64 | cores 32-47 | 6/6 PASS | 6 isolated hermetic negative controls verified |
| `python3 tools/run_known_motion_gates.py` | local & cpu64 | cores 32-47 | PASS | 9/9 gated metrics passed, thread/dose-weighting invariance confirmed |
| `python3 tools/test_known_motion.py` | cpu64 | cores 32-47 | 27/27 PASS | Unit checks, fixture self-validation, negative controls, noise floor |
| `python3 tools/test_known_motion_verdicts.py -v` | cpu64 | cores 32-47 | 8/8 PASS | Verdict controls pass |
| `python3 tools/test_known_motion_runner.py -v` | cpu64 | cores 32-47 | 8/8 PASS | Runner controls pass |
| `python3 tools/test_compare_motioncorr.py -v` | cpu64 | cores 32-47 | 20/20 PASS | Comparator failure controls pass |
| `BUILD_TESTING=OFF` configure & build | cpu64 | cores 32-47 (j8) | PASS | Preserves independence from Python/numpy for builds without testing |

## Compute & Resource Adherence

- Host: `cpu64` (`small-refmac-machine`).
- Lock: `/tmp/motioncorr-issue96-cpu-validation.lock` strictly acquired via `flock`.
- CPU topology & binding: socket 1 / node 1, `taskset`/`numactl --physcpubind=32-47 --membind=1`. Parallelism <= 8 (well within <= 16 limit).
- Background interference recorded: two long-running ctffind processes preserved untouched.
- **NEEDS_GPU: no.** GPU execution strictly avoided; preserved for issue #26 coordinated slot. CUDA compilation tested in CI via Docker container `nvidia/cuda:12.8.0-devel-ubuntu24.04` with package dependencies including `python3-numpy`.
