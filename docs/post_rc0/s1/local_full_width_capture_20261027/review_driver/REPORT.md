# Full-width capture execution package: driver/admission/witness review r1 (Opus, read-only)

**Verdict: CLEAR conditional on C1 and C2.** Both are small driver edits. Each edit changes the driver sha256, so the pins (`prep_files`), RELEASE_BINDINGS and PARENT_RELEASE must be regenerated and `--check-only` re-run. N1–N5 do not block release. I did not re-audit the C++/GPL source; it is taken as CLEAR from report `bdea0d80…0f00`, whose hash I verified.

## Bound identities (verified by hash)
Worktree HEAD `33a167e0a9f187cc6294f6cb430e0ea54201e444`, clean. All inputs below were verified by hash:
- run_capture_fw.py `74678396…e765`
- CAPTURE_RUN_PINS.json `2548da9b…a32f`, byte-equal to `receipts/cpu64/RUN_PINS.json`
- COMMANDS_CAPTURE.json `26eeea36…ac0c`, byte-equal to the cpu64 copy
- RELEASE_BINDINGS.json `7e9036fa…31e5`
- capture_witness.py `1206fe46…4768`
- weight_oracle.py `d809bd62…7ee8`
- guard/lane/verify_source equal their `receipts/cpu64/prep` copies and their pinned hashes
- source review REPORT.md `bdea0d80…0f00`

No PARENT_RELEASE exists, and this review writes none.

## What holds
- **Commands.** The OFF and ON argv and environment, derived exactly as `run()` derives them, equal the frozen COMMANDS_CAPTURE.json (T1). The two jobs differ only in `MC_DIAG_LOCAL_CCF_DIR` and the run paths. The environment shape (pinned env plus `PATH=/usr/bin:/bin`) matches the sealed baseline producer (`driver_v5_2.py:360-361`).
- **Pre-launch checks.** They cover the interpreter, NumPy, review verdict, prep files, source blobs, binary, the 18 libraries as an exact set, the loader, the comparator, ROOT_AUDIT, baseline RUN/products/extra files, and inputs and their scope. The per-job live admission checks the exact pinned 8 locks, affinity 32-47, foreign occupancy, the 6-root 25 GiB scratch cap, disk and memory. The admission sits inside `run()`, so it is fresh for each job.
- **Stop and attempt rules.** EVID uses `exist_ok=False`, so there is one attempt. A STOP is written once EVID exists. ON runs only after OFF identity and the OFF log witness pass, and OFF must have no capture directory.
- **Witnesses.** The packaged witness tests re-run locally with the existing generator (`0512162c…5552`), the real pilot logs and the real old capture: rc 0, **PASS 32 checks**, max RSS 33 MB. The expected-file rule reproduces the real old capture exactly: 302 files per patch, both patches equal, 604 in total.
- **Weight oracle.** It discriminates 42 from 22, and W3 requires both exact equality with 42 and inequality with 22. The Linux native control (0 differing bins for each of 42 and 22, 624/704 bins different between them) is producer-reported and consistent with the pinned files.

## Conditions (must fix before the parent release)
**C1 — Binary and staged inputs are not re-verified before each launch.** At `driver/run_capture_fw.py:73-93` (admission) and `:121-136` (run):
- The reviewed `run_capture.py` admission re-hashed the binary, sources and inputs on every job. The new admission dropped these checks.
- The binary is hashed only once, in `pre_checks` (`:53`). `run()` records `binary_sha256` in RUN.json (`:132`) but never compares it with the pins.
- The staged `native-input` is hashed once, at staging (`:154`).

Scenario: the binary or `native-input/noisy.*` changes between `pre_checks` and the ON launch, after OFF has already passed. ON runs anyway, and its RUN.json silently carries a non-pinned hash.

Fix: in `run()`, immediately before `Popen`, check `sha(binary) == pins` and the staged input hashes and scope. After the run, check `receipt['binary_sha256'] == pins['binary_sha256']`. (T4)

**C2 — No per-file hash inventory of the capture.** At `:159-166`, the writer's records (COMPLETE.json, session.json, patch-files.json) contain names and byte totals only, with no hashes (T5). The driver hashes `output/` only. The analysis plan requires the capture record to be "sealed" and pinned by hash before any read.

Scenario: a capture file is altered after the witnesses pass, and nothing bound at production time detects it.

Fix: after `run_all` passes, write `capture-inventory.json` with `{relpath: {bytes, sha256}}` for every file under `on/capture`, check that the file count equals the coverage total, and put the inventory sha256 into NATIVE_COMPLETE.json. The alternative is that the parent explicitly owns this step at sealing, but then it is outside the frozen driver.

## Non-blocking
- **N1** — Malformed witness inputs raise `TypeError`, `KeyError` or `AttributeError`, not `Stop`. Five reproduced cases on the real capture: `bytes_before_complete: null`, patch-files.json without `files`, and session/weights/peak JSON given as a list (T3). These escape `except CW.Stop` (`:163`) with rc 1, no STOP.json and no capture-witnesses.json. The run still fails closed, because NATIVE_COMPLETE is not written. Suggest `except Exception as e: check(False, ...)`.
- **N2** — `fresh_resource_grant` is checked only for truthiness (`:41`). `"stale grant…"`, `1` and `{"cpus":"0-63"}` are all accepted (T2). The live per-job admission enforces the actual resources; if the grant is meant to bind anything, require structured fields (utc, cpus `32-47`, `lane_locks`).
- **N3** — The monitor receipt (`:95-110`) is written but never validated after the run. The baseline run took 0.13 s, and the old capture campaign's monitor got 2 samples per job, one of them empty. A run with no `motioncorr` sample would still be accepted. Suggest requiring at least one sample that names `motioncorr` with `allowed == '32-47'`. No new tolerance is needed.
- **N4** — No timeout, no SIGTERM handler and no process-group or PDEATHSIG cleanup. This is inherited from `run_capture.py`; the pilot `driver_v5_2.py:212-235` had all of them. If the driver is killed during the ~0.2 s producer, the child is orphaned while the lane leases drop.
- **N5** — Documentation and packaging:
  - README:17 says "18 negative controls". The script and `receipts/negctl_precheck.txt` contain **17** refusals plus the positive.
  - PACKAGE_SHA256SUMS lists two gitignored `driver/__pycache__/*.pyc` files (mtime 01:01, before this review). A clean checkout therefore verifies 128/130.

## Not done / UNRUN
I did not use SSH, a movie, pixels, a build, a producer or the GPU. The Linux receipts are producer-reported and I inspected them only. The driver's `run()`/`admission()`/`monitor()` were reviewed statically, because they need Linux `/proc`, `ps psr` and `time -v`. The native witnesses remain UNRUN. A CLEAR here is not scientific acceptance.

## Files
- `scripts/review_tests.py`: T1–T6. It uses byte-identical copies of the pinned driver, witness and oracle, with ROOT redirected to a private temp dir.
- `scripts/old302.py`
- `results/*.json`, `results/*.out`, `results/*.rc`: test_capture_witness rc 0, review_tests rc 0, generator sha.

Local run limits: Python 3.13.7 with NumPy 2.3.2, which is not the pinned 3.12.3/2.5.3, so the oracle equality on cpu64 remains producer-reported; at most 2 threads; peak RSS under 40 MB.
