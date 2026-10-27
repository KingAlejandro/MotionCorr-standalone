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

## Delivery (added after the work; the amendment above is unchanged)

Source commit for review: see the pushed HEAD; code bytes are fixed at `72f4b7d9` (everything above it is evidence and docs). Production `src/`, `tests/`, `test-data/` and the reviewed tools (`ccf_dc_native_rows.py`, `ccf_dc_tap_field.py`, `check_*`, `motion_field.py`) are unchanged since `96e7e7be`. No Stage C producer, release file or native row exists.

| File | sha256 |
|---|---|
| `tools/stageC_guard.sh` | `ad10f27e4a0d17900342cf5fe1ae902eea9c84b6aae7bc1248707dc9ab34dd6d` |
| `tools/ccf_dc_stagec_driver.py` | `daee5f14296e8af0b2b5a6e595fbe48d4b9ce52dd93645b5e864da01fa973e00` |
| `tools/test_ccf_dc_stagec_guard.py` | `3cbb04d5c37dc1d2acc108a053c28294da1b9c7cbc88f5722a4c00978c481088` |
| `tools/test_ccf_dc_stagec_lifecycle.py` | `3dc75346215d151733a3b895a75f67b52b14afd20a5ebd0ebd26b962445ce109` |
| `evidence/stageC/amend1_window.sh` | `5a538a6d4365e0e53ffe971389020757f3a5edfd86dc98cbfb1a20f4fe97b4d6` |
| `evidence/stageC/STAGEC_PINS.json` (regenerated; guard pin `ad10f27e...`) | see `PINS.json` index |

Attempts, all kept:
1. `b7935fd5` driver, guard and pins: preserved (`STAGEC_PINS.b7935fd5.json`, git history). The parent's pre-review found the fail-open guard and the missing process record, which this amendment fixes.
2. First full driver-suite run on the amended bytes (`amend1_logs/driver-suite-run1.FAILED-stale-pins.out`, 19 tests, 227.0 s): 18 passed, 1 failed, `test_committed_pins_match_the_repository`, because the committed pins still held the old guard sha256 `95b82554...` (it correctly caught stale pins, not a guard-logic failure). The pins were then regenerated by `make_stagec_pins.py` and the pin tests re-run (3 OK).
3. Clean full driver-suite run on the final bytes (`amend1_logs/driver-suite-run2.OK-19of19.out`): 19 tests, OK, exit 0, 226.5 s. This is the single 19/19 run.

Guard tests (8, fake `nvidia-smi`/`ps`/`df`/`du`/`free` shims and `/proc/stat` fixtures): the `b7935fd5` guard fails all 8; three fail-open mutants (granted-GPU numeric check removed, bad CPU delta read as 0, missing-core check removed) are each caught; the amended guard passes all 8 locally (macOS) and on the venue (Linux). Lifecycle tests (12, fake children only): pass locally and on the venue; on Linux the sampling record is OBSERVED with child and grandchild, tree size at least 2, threads at least 3, allowed-CPU list and names recorded; timeout, `KeyboardInterrupt`, other exceptions, `SIGTERM` and a straggler all leave no child alive and keep the failure; a spawner that raises is a STOP with the exception text; a short row is never given invented numbers.

Venue window (4GPUs, 2026-10-26 23:03:16Z - 23:03:42Z, subset archive sha256 `c48a59fd7e8a1feaed369fcf2a6d0b46bd77287015a3be733b7a2792af702bed`, leases own + cpu80-87 + gpu2-correctness non-blocking, affinity 80-87, CPython 3.12.3, NumPy 2.5.3; logs in `amend1_window/`, `SHA256SUMS`): the standalone guard, real entry (`STAGEC_REAL=1`), ran once read-only: exit 0; all four GPUs listed, GPU2 `GPU-063e5232-...` 425 MiB, 0 % utilisation, only the foreign PID 3983855 present on it, cores 80-87 0 % busy, scratch used 18690219 bytes against the 20 GiB cap, df available 634833575936, memory total 464899809280 and available 447750787072. Guard tests on Linux: 8 OK. Lifecycle tests on Linux: 12 OK. No MotionCorr child, no GPU producer, no retry. GPU3 stayed at 88 % under the foreign process (not used). No performance or exclusivity claim.

Resource claim unchanged: thresholds as before (GPU2 utilisation 50 %, a core 50 %, foreign PID 3983855 allowed). The review brief asks the operator for a fresh GPU2 baseline (0 % utilisation, the foreign context only) as the grant condition; nothing is broadened.

Still UNRUN: any Stage C producer; the real graders under the driver; B3 across `def` and `exp`; CUDA sampling with a real CUDA child (the nvidia-smi mapping path is exercised only by its code, not by a fake CUDA child); everything in the 160 K267/N rows and the 16 M rows.
