# Stage C plan amendment 1 (written before the fixes, tests or code; nothing here has run)

Reason: the parent's pre-review inspection of `b7935fd5` found a fail-open guard and no per-row process/thread record. `b7935fd5`, its `STAGEC_PINS.json` (kept as `STAGEC_PINS.b7935fd5.json`) and every earlier record stay as history. No native job, no C++ change, no release file; all 160 K267/N rows and the 16 M rows remain HELD. Same scope, same ledger, same order, same thresholds.

## 1. Guard fails closed (MATERIAL)

`tools/stageC_guard.sh` currently prints and passes when a required read fails (an empty utilisation makes `[ "" -gt 50 ]` error but the script still ends 0; a missing `/proc/stat` row leaves the busiest-core value 0). The plan already said an unreadable resource stops the campaign; the guard now enforces it:

- Every required command (`nvidia-smi` GPU query, `nvidia-smi` compute-app query, the two `/proc/stat` reads, `ps`, `df`, `free`, `du`, `mktemp`) must exit 0 and parse. Otherwise the guard exits non-zero with a specific code, never 0: 11 other compute app on GPU2, 12 GPU2 utilisation above the unchanged 50 %, 13 a core of 80-87 above the unchanged 50 %, 14 a command failed, 15 empty, malformed or non-finite data, 16 scratch accounting failure, 20 a test hook present in a real run.
- Required valid values: the exact GPU2 UUID present exactly once in the GPU table with numeric memory and utilisation in range; every compute-app line well formed; all eight cores 80-87 present in both `/proc/stat` samples with a positive total delta (a missing or zero-delta core is a stop, not 0 %); `df` available bytes numeric; scratch used numeric and not above the frozen 20 GiB cap, and `df` available at least the room left under that cap; `free` total and available numeric and consistent. No new threshold is added.
- Hygiene: `set -u -o pipefail`, quoted variables, `mktemp -d` with an `EXIT` trap, no signal to any foreign process.
- Test hooks (command shims on `PATH`, `/proc/stat` fixtures, no sleep) exist only when `STAGEC_TEST_MODE=1`; the real entry (`run`) sets `STAGEC_REAL=1` for the guard and refuses to start if any `STAGEC_TEST_*` variable is in its own environment, and the guard exits 20 if a test hook and `STAGEC_REAL=1` coexist.
- The standalone guard is run once, read-only, on 4GPUs under the non-blocking leases and a fresh CPU 80-87 allocation (no GPU producer), its stdout and exit status retained; no automatic retry if a foreign process makes it stop; no performance or exclusivity claim.

## 2. Per-row process and device record, and child lifecycle

`CPU affinity + OMP 8/2` does not show what a process actually ran. Each producer now gets: an immediate and then bounded periodic (every 0.5 s, at most 240 samples, truncation recorded) `/proc` sample of the child and its descendants: pid, ppid, name, state, `Threads`, task count, `Cpus_allowed_list`, utime/stime ticks; and, for CUDA rows, a `nvidia-smi --query-compute-apps` sample mapping pids in that tree to GPU UUIDs. Output: `procsamples.jsonl` in the run directory and a summary in the receipt (samples, maximum tree size, maximum threads and tasks, allowed-CPU lists seen, names, GPU UUIDs seen per pid, read errors, truncation). A row too short to be sampled, an unreadable `/proc` or an absent mapping is recorded `UNOBSERVED` or with the read errors; nothing is rerun to obtain a witness and nothing new stops on a thread count or on an unexpected CPU list (recorded only). Normal stdout/stderr, argv, environment and stopping rules are unchanged.

Lifecycle: the child runs in its own session/process group (`PR_SET_PDEATHSIG` via `ctypes` on Linux, no new dependency). On timeout, any ordinary exception, `SIGTERM` or `KeyboardInterrupt` the driver terminates the group (TERM, short wait, KILL), records the actual exit or exception in the receipt, appends a STOP with that text, writes the manifest and only then releases the leases. First failures are captured; there is no hidden retry.

## 3. Resource claim unchanged

The Stage C resource proposal has not been released. The declared guard thresholds are unchanged (GPU2 utilisation 50 %, a core 50 %, foreign PID 3983855 allowed). The review brief will ask the operator for a fresh GPU2 baseline (0 % utilisation, the foreign context only) as the grant condition. If a stricter threshold is wanted it must be frozen in new pins before any outcome, never after results; nothing is broadened silently.

## 4. Tests and pins

Pure tests with fake `nvidia-smi`, `ps`, `df`, `free` shims and `/proc/stat` fixtures: command exit non-zero, empty or non-numeric output, malformed GPU row, wrong or missing UUID, missing or zero-delta core, unreadable resource, scratch above the cap, a valid realistic fixture passes, test hooks in a real run rejected. Driver tests with fake children only (at most 2 threads, 150 MB scratch, 1 GB memory): sampling records a child and a grandchild, timeout and exception and `SIGTERM` leave no child alive and keep the failure, a spawner that raises is a STOP with the exception text, no sample is invented. A Linux run of the sampling and lifecycle tests is allowed once on 4GPUs under fresh leases (fake children only, no MotionCorr child). `STAGEC_PINS.json`, `PINS.json` and the CTest list are updated and versioned; the original pins are preserved.
