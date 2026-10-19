# Pre-freeze shakedown of `tools/asan_eer.sh` on `cb3699ac`

This is a shakedown of the item 15b tool on current main `cb3699ac73c8af20ed47f52a0be8504a049b03e1`, run so the
script is not executed for the first time at freeze. **It is not an item 15 result:** item 15 runs on the frozen
SHA F, on 4GPUs, with the default lock and venv.

Host cpu64 (`small-refmac-machine`), g++ 13.3.0, CMake 4.4.3 and Python 3.12.3 + NumPy 2.5.3 from
`/home/ubuntu/.mc-venv`, CPUs 40–47, 2026-10-18. Workspace
`/home/ubuntu/mc-rc0-paired-20261017/W-QF-asan-shakedown-cb3699ac/` (a git clone checked out at `cb3699ac`, 0
modified files; the ASan build tree was deleted after recording). As instructed, no bench lock was taken:
`QF_BENCH_LOCK` pointed the script's probe at a private file in the workspace, and the cpu64 bench lock
(`/tmp/motioncorr-cpu64-bench.lock`) was checked free in `/proc/locks`, without being taken, before and after each
run. Nothing was timed.

| | Attempt 1 | Attempt 2 |
|---|---|---|
| Tool sha256 | `8f6c9798…2d2ca770` | `847357f6…76d5885b` (committed at `a5d3a26a`) |
| Source | `cb3699ac`, clean | `cb3699ac`, clean (fresh build tree) |
| Configure / build | rc 0 / rc 0 | rc 0 / rc 0 |
| Instrumentation | `-fsanitize=address,undefined` in `flags.make`; `motioncorr` and `runner_numerics` linked to libasan.so.8 and libubsan.so.1 | same (`attempt2-pass/identity.txt`) |
| Binaries (sha256) | `motioncorr` `e04e7d3d…aa742396c`, `runner_numerics` `08ec9239…d15e23ae` | identical to attempt 1 |
| `EerMemorySafety` | Passed, 33.95 s | Passed, 33.63 s |
| Sanitizer reports | 0 lines in the CTest output; the test itself fails on any sanitizer line in a child log | 0, same |
| Decoder sources = `97fb9fda` | yes | yes |
| Exit status | **1 (FAIL): tool defect** | **0 (PASS)** |

**Attempt 1 defect.** The script required CTest 3.x's summary `100% tests passed, 0 tests failed out of 1`.
CMake 4.4.3 prints `100% tests passed out of 1`, so a passing test was graded FAIL. Fixed in attempt 2's tool:
either summary form is accepted, and the CTest output must also contain the line
`Test #N: EerMemorySafety ... Passed`. That predicate accepts both real summaries (this run and #231's 4GPUs
CMake 3.28 log) and rejects a failed test and a run that executed a different test. Attempt 2's tool also adds
the optional `QF_VENV` and `QF_BENCH_LOCK` (defaults unchanged: the 4GPUs venv and bench lock) and prints the
sanitizer line count.

Records: `attempt1-fail/` and `attempt2-pass/` (`asan-eer.log`, `asan-eer.ctest.log`, `asan-eer.exit`,
`tool-sha256.txt`; `identity.txt` for attempt 2).

The tool was revised after this shakedown, at `6adf0ad6` (sha256 `aeed6e06…b62f3b`): it now prints a `WARNING` line
when `QF_BENCH_LOCK` is not the default. No other behaviour changed, so the shakedown was not repeated.
