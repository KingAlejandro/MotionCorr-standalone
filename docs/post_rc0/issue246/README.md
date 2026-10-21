# #246 ProfilingKit compiler-settle control

Base: `c8844894c7c6366abf297699b5312e4b775eb5b0`. Negative control: `b1c01bcaa1b8fd7801bb27c692c226eb1cb8709c` (base plus the live-compiler fixture, with the old CLI arguments). Fixed implementation head: `927e5b5cfa51cf72187f182ecffd0693111c71f7` (only the addition of `--settle-timeout 0` differs from the negative control).

The two fake-payload import/subset CLI tests used a 30-second subprocess deadline but left `mcprof run`'s 300-second compiler-settle default enabled. `provenance.compilers_running()` scans every Linux `/proc/*/comm` for `cc1`, `cc1plus`, `nvcc`, `cicc` and `ptxas`; even a sleeping compiler-named process on another CPU can therefore cause the timeout. This is not a RelionError regression or a numerical/performance gate failure.

The shared argument list now passes `--settle-timeout 0`, matching the other fake CLI tests. Production defaults, the existing 30-second test deadline, numerical gates, and all STAR/subset/product assertions remain unchanged.

On Linux each CLI case copies the system `sleep` executable to a private file named `cc1`, starts it, and verifies that the production compiler scanner sees its PID/comm. The fixed cases additionally require that the process is still alive after CLI completion and that the CLI's settle provenance records that same compiler witness. A `finally` block terminates and reaps only that child. On platforms without `/proc`, the original functional CLI checks still run; the Linux-only compiler mechanism is not asserted.

Native 4GPUs results, CPUs **72–79** (`taskset`, eight CPUs), `TMPDIR=/tmp`, Python `~/.mc-venv/bin/python3`:

- Negative control: `ctest -R '^ProfilingKit$' --output-on-failure`, exit **8**; 134 internal tests, exactly the two target CLI cases error with `TimeoutExpired` after 30 seconds. Dummy compiler witnesses: `2001158:cc1`, `2002977:cc1`.
- Fixed head: the same command, exit **0**, **134/134 internal tests pass**, no skips. Dummy witnesses: `2009946:cc1`, `2009975:cc1`; both remain alive through successful CLI completion, with matching settle provenance.

The source trees were copied with `git archive`, retain Git metadata for provenance, and were clean before/after execution. Release CMake configuration succeeded for each arm (`-DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON`). No C++ build was required or claimed. The wrapper held `/tmp/motioncorr-bench.lock`, waited for other agents' active selftests to finish before creating a dummy compiler, and released the lock on completion (independent post-run probe rc 0). Other jobs were left alone. This is a correctness control, not a timing comparison; no GPU was used.

`run.sh` retains the commands. `native/ctest-{before,after}.{log,xml,exit}` retains raw results; the passing JUnit captures the 134-test summary and compiler witnesses. Occupancy, source SHAs and configure logs are adjacent.

Re-entry class: tests only (§9.4); affected ProfilingKit rerun complete. UNRUN: full CTest, QF, native GPU execution, performance and scientific campaigns. No gate or tolerance was changed.
