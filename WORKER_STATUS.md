# WORKER_STATUS — issue #72

| field | value |
| --- | --- |
| issue | #72 — Fail-closed CI and canonical fixtures |
| model | `gemini-3.8-flash-high` via Antigravity (`antigravity`, displayed Alexgravity) |
| task class | validation |
| phase | 5/5 — Review findings addressed, validated on cpu64, committed & pushed |
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| head | `078cf6e36a44ec1b777e4820e10d3dc82dc08296` |
| branch | `round96/72-gemini-3-8-flash` |
| worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-1d15fa94` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/102 |

## Declared changed-file whitelist

This task does **not** modify the production pipeline or GPU kernels. It addresses CI failure-policy gaps, CMake test dependency enforcement, fixture integrity verification, and negative controls.

| path | status | kind | scope / role |
| --- | --- | --- | --- |
| `agents/designs/issue_72_fail_closed_ci_canonical_fixtures.md` | new | ADR | Architectural design record |
| `WORKER_STATUS.md` | new | handoff | Round 96 status handoff |
| `.github/workflows/ci.yml` | edit | CI | Use Python 3.12 & numpy>=2.4.0, add explicit fixture generation & pre-gate verification, call `ci_preflight.py` |
| `CMakeLists.txt` | edit | build | Enforce Python3 and numpy when `BUILD_TESTING=ON` (leave `BUILD_TESTING=OFF` independent), additive test registration |
| `test-data/generate_known_motion_fixture.py` | edit | fixture | Added `--canonical` and `--refuse-conflicting` modes, prevent stale truth pairing, guard manifest rewrite behind `--write-manifest` |
| `tools/ci_preflight.py` | new | tool | Maintained entrypoint asserting all 16 required CI scripts and canonical truth files exist and are non-empty |
| `tools/verify_fixtures.py` | new | tool | Strict manifest schema validation, mandatory truth file presence/hash checks, fail-closed git lookup (no silent disk fallback) |
| `tools/validate_test_collection.py` | new | tool | CTest suite collection validator (requires 14 tests, including `CiFailClosedControls`) |
| `tools/run_known_motion_gates.py` | edit | tool | Inventory check before case discovery; gate execution with `--no-regenerate` |
| `tools/test_ci_fail_closed.py` | new | test | 7 isolated negative controls testing actual maintained entrypoints, real CMakeLists.txt, pre-asserted baseline, and quoted interpreter |

Explicitly **not** touched: `src/**`, `src/acc/cuda/*`, reference output data, numerical thresholds or tolerances, Actions permissions.

## Root Cause Analysis: Canonical Fixture Identity in CI

A bit-for-bit byte, header, and pixel comparison between GitHub Actions run 36360660020 generated movie `4e8666c1...` and canonical fixture `f9da4668...` (`km_global_hisnr.mrcs`) revealed:
1. **Pixel Data (3,145,728 float32 values)**: 100.000000% bit-for-bit identical! Exactly 0 mismatched pixels ($\text{max\_diff}=0.0$, $\text{rms}=0.0$).
2. **MRC Header (1,024 bytes)**: Exactly 1 byte differed at offset 216 (`0x0d8`): byte was `0xdd` vs `0xdf`.
3. **Source of Difference**: Offset 216 is the IEEE-754 single-precision float for `RMS deviation of map from mean` (`struct.pack_into("<f", header, 216, float(stack.std()))`). NumPy modified pairwise summation vectorization in `std()` in NumPy 2.4.0, resulting in a 1-ULP ($9.5367 \times 10^{-7}$) difference in float32 representation (`6.01365518...` vs `6.01365613...`).
4. **Environment Divergence**: `.github/workflows/ci.yml` previously configured `python-version: "3.10"`. NumPy $\ge 2.4.0$ requires Python $\ge 3.11$, so `pip install 'numpy>=1.24,<3'` on Python 3.10 installed `numpy==2.2.6`. On Python 3.12 (the supported modern environment on Linux `cpu64` and macOS), `pip install 'numpy>=2.4.0,<3'` installs NumPy $\ge 2.4.0$ and generates bit-exact canonical files.
5. **Resolution**: Workflow updated to `python-version: "3.12"` and `numpy>=2.4.0,<3`, restoring complete byte parity across all 4 canonical fixtures.

## Review Item Reconciliation

1. **[P1] Canonical fixture identity in CI**: Identified root cause (Python 3.10 / NumPy 2.2 vs Python 3.12 / NumPy 2.4 std() 1-ULP float header difference at offset 216; pixels 100% bit-exact). Standardized CI on Python 3.12 with `numpy>=2.4.0,<3`.
2. **[P1] Truth file and manifest validation in `verify_fixtures.py`**: Added strict schema validation for manifest inventory (empty `cases` fails closed); required declared ground-truth JSON files to exist and match hashes; distinguished excluded heavy cases from verified cases and ensured zero verified cases fails with exit 1.
3. **[P1] Trusted Git lookup fails closed**: Removed silent fallback to mutable disk manifest upon git lookup failure. Default mode fails closed with exit 2 if ref cannot be loaded; explicit `--manifest` required for offline/file-based manifests.
4. **[P1] Step order and inventory check**: Separated fixture generation (`test-data/generate_known_motion_fixture.py --canonical`), fixture verification (`tools/verify_fixtures.py`), and numerical evaluation (`tools/run_known_motion_gates.py --no-regenerate`). Gated inventory is checked before case discovery.
5. **[P2] Hardened negative controls in `test_ci_fail_closed.py`**: Tested actual maintained entrypoint `tools/ci_preflight.py` and real `CMakeLists.txt` directly; provided full required CLI arguments to `run_known_motion_gates.py`; required `CiFailClosedControls` in collection validator.
6. **[P2] Generator protection**: Added `--canonical` mode to verify against canonical truth and refuse drift, added `--refuse-conflicting` to prevent parameter collision, and ensured ordinary generation always pairs matching truth with newly generated movie bytes. Added negative control 7.
7. **Baseline assertion and quoting**: Control 5 asserts passing baseline before corrupting movie byte; interpreter paths quoted in stub wrappers. Reconciled commit references in `WORKER_STATUS.md`.

## Tests & Validation

All tests executed and verified on both local macOS (arm64) and remote Linux (`cpu64` / `small-refmac-machine`, x86_64, Ubuntu 24.04, node 1 / cores 32-47, under `flock /tmp/motioncorr-issue96-cpu-validation.lock`):

| command / suite | host | cores / node | result | notes |
| --- | --- | --- | --- | --- |
| `python3 tools/ci_preflight.py` | local & cpu64 | cores 32-47 | PASS | All 16 required CI scripts and canonical truth files verified |
| `python3 tools/validate_test_collection.py --test-dir build` | local & cpu64 | cores 32-47 | PASS | Enforces collection >= 14, all required test targets present |
| `ctest --test-dir build --output-on-failure` | cpu64 | cores 32-47 (j8) | 14/14 PASS (100%) | Includes bit-for-bit exact `SyntheticRegression` and `CiFailClosedControls` |
| `python3 tools/verify_fixtures.py --fixtures-dir test-data/known_motion` | local & cpu64 | cores 32-47 | PASS | Compares all 4 fixtures against canonical `git:HEAD:test-data/known_motion/MANIFEST.json` |
| `python3 tools/test_ci_fail_closed.py -v` | local & cpu64 | cores 32-47 | 7/7 PASS | 7 isolated negative controls testing actual maintained entrypoints |
| `python3 tools/run_known_motion_gates.py --no-regenerate` | local & cpu64 | cores 32-47 | PASS | 9/9 gated metrics passed, characterization failure visible |
| `python3 tools/test_known_motion.py` | cpu64 | cores 32-47 | 27/27 PASS | Unit checks, fixture self-validation, negative controls, noise floor |
| `python3 tools/test_known_motion_verdicts.py -v` | cpu64 | cores 32-47 | 8/8 PASS | Verdict controls pass |
| `python3 tools/test_known_motion_runner.py -v` | cpu64 | cores 32-47 | 8/8 PASS | Runner controls pass |
| `BUILD_TESTING=OFF` configure & build | cpu64 | cores 32-47 (j8) | PASS | Preserves independence from Python/numpy for builds without testing |

## Compute & Resource Adherence

- Host: `cpu64` (`small-refmac-machine`).
- Lock: `/tmp/motioncorr-issue96-cpu-validation.lock` strictly acquired via `flock`.
- CPU topology & binding: socket 1 / node 1, `taskset`/`numactl --physcpubind=32-47 --membind=1`. Parallelism <= 8 (well within <= 16 limit).
- Background interference recorded: two long-running ctffind processes preserved untouched.
- **NEEDS_GPU: no.** GPU execution strictly avoided; preserved for issue #26 coordinated slot. CUDA compilation tested in CI via Docker container `nvidia/cuda:12.8.0-devel-ubuntu24.04` with package dependencies including `python3-numpy`.
