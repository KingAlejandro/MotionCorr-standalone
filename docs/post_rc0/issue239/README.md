# #239 RelionError backtrace ownership

Implementation head: `1c14e8882b4754903da4499f1ceca5fd8037f630`, based on `c8844894`.

The backtrace remains at most 100 frames with the same symbol rendering, delimiters and error text. `std::vector<void*>` owns the address array by value: implicit copies own independent storage, destruction releases unprinted errors, and printing only observes the array. `backtrace_symbols`' separate C allocation is still freed after rendering. Upstream notices remain intact; no dependency, numerical gate, product or metadata change.

The regression captures constructor stderr exactly, constructs the expected backtrace from its recorded addresses, and checks throw-by-value, catch-by-value, copy, assignment and repeated printing against that string. `--unprinted` throws/catches eight errors without printing for LeakSanitizer. Both tests are collected in every configuration (F counts 74/108/111 become 76/110/113).

Reproduction scripts are retained here. Sources were transferred with a Git bundle based on `c8844894`, fetched into an isolated clone on 4GPUs. Direct SSH timed out while the VPN was down; `ssh -J ccp4-gateway 4GPUs` succeeded. Native scratch is `/mnt/clathrin/alex-motioncorr-hygiene239`, CPUs 112–119 (taskset, eight CPUs), GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, lock `/tmp/motioncorr-gpu3-correctness.lock`. The bench lock is probed before builds and each CTest batch. Other agents' GPU1 and CPUs 64–71/104–111 work was left alone. These are correctness runs, with no performance claim.

Local macOS arm64 preliminary evidence: Release unit CTests 2/2 passed; AddressSanitizer reported double-free before and no error after. Local LeakSanitizer is unsupported; the required leak controls therefore ran on Linux, not on macOS.

Native results (GCC 13.3.0, CUDA 12.8.61, A100 80 GB; full provenance/flags/hashes in `native/`):

- All three Release configure/build pairs exited 0. Collection validation passed for each configuration.
- Before: LeakSanitizer reports **6,400 bytes in eight allocations** from `error.cpp:58` on `--unprinted` (exit 77). Copy/print reports AddressSanitizer heap-use-after-free (exit 77).
- After: unprinted and copy/assignment/throw/repeated-print paths both exit 0 with `ASAN_OPTIONS=detect_leaks=1:exitcode=77`, with no sanitizer output.
- Full CPU CTest: **75/76 passed, FAIL** (exit 8), no skips; only ProfilingKit failed, with two unchanged 30-second CLI subprocess timeouts. **Root cause: [#246](https://github.com/KingAlejandro/MotionCorr-standalone/issues/246), a test-harness defect, not RelionError ownership.** The fake-payload CLI calls omit `--settle-timeout 0`, so `runner.settle()` can wait 300 seconds for any host compiler while the test kills its subprocess after 30 seconds. No performance inference is made.
- Full CUDA CTest: **110/110 passed** (exit 0), no skips, native GPU3 under its lock.
- Full CUDA+nvCOMP CTest: **113/113 passed** (exit 0), no skips, native GPU3 under its lock.
- The one permitted CPU ProfilingKit rerun, after all other validation from this task finished, also **FAILS** (0/1 CTest, exit 8; 134 internal tests, two 30-second CLI timeout errors). It is retained separately and does not relabel the original full run. The original run ended after that permitted rerun; the later #246 control is a discriminating test-harness experiment, not another rerun of #245.

Qualification outside the error/failure routes covered by full CTest was not rerun: full QF route/product replay, independent scientific acceptance and performance qualification retain their earlier revisions. No numerical or output-parity change needs maintainer sign-off. **The CPU re-entry question for #245 is resolved by the independent #246 harness root cause; no maintainer decision or waiver is needed for these two timeouts.** The historical 75/76 and failed rerun remain FAIL records.

## #246 attribution

The retained [occupancy snapshot, lines 10–17](native/cpu-profiling-rerun-occupancy.txt#L10-L17) records live `cc1`/`cc1plus` processes during the failed rerun (load average 29.81 at line 2). Compiler **presence anywhere on the host**, rather than CPU saturation itself, is the trigger: `provenance.compilers_running()` scans `/proc/*/comm`; `runner.settle()` waits for that set to empty. The missing test option permits a 300-second settle wait inside a 30-second subprocess deadline. Other CLI tests already disable this settling for fake payloads. RelionError is not on this Python test path.

The separate [#246 fix, PR #247](https://github.com/KingAlejandro/MotionCorr-standalone/pull/247), provides the affected-test evidence: full ProfilingKit on 4GPUs fails before with the same two timeouts while a verified sleeping `cc1` is present, then passes **134/134 internal tests** after adding `--settle-timeout 0`. Each fixed CLI case verifies that the compiler is still alive and recorded in settle provenance. See [the retained control evidence](https://github.com/KingAlejandro/MotionCorr-standalone/blob/fix/246-profiling-settle/docs/post_rc0/issue246/README.md). The subsequent cpu64 proposal was superseded by the maintainer's #246 instruction; its full suite was interrupted and is not used as re-entry evidence.
