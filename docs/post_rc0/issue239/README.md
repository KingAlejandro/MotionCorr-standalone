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
- Full CPU CTest: **75/76 passed, FAIL** (exit 8), no skips; only ProfilingKit failed, with two unchanged 30-second CLI subprocess timeouts. This matches its documented load-sensitive failure class. That run overlapped this task's #240 checks on the same eight-CPU mask; this may have contributed to scheduling delay. No performance inference is made.
- Full CUDA CTest: **110/110 passed** (exit 0), no skips, native GPU3 under its lock.
- Full CUDA+nvCOMP CTest: **113/113 passed** (exit 0), no skips, native GPU3 under its lock.
- The one permitted CPU ProfilingKit rerun, after all other validation from this task finished, also **FAILS** (0/1 CTest, exit 8; 134 internal tests, two 30-second CLI timeout errors). It is retained separately and does not relabel the original full run. No further rerun was attempted.

Qualification outside the error/failure routes covered by full CTest was not rerun: full QF route/product replay, independent scientific acceptance and performance qualification retain their earlier revisions. No numerical or output-parity change needs maintainer sign-off. **Maintainer disposition of the retained CPU ProfilingKit failure is required before accepting re-entry; this report does not grant it.**
