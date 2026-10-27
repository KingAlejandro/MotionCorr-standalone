# Stage C driver delta review r2 (Opus, read-only)

Target: PR289 worktree `t3-9c391c37`, HEAD `047aa7a51381ca074dcf4c468581108ce551c3ed` (clean); delta from the r1-reviewed head `26e74d8a`
(commits `184741a8` response plan, `047aa7a5` fixes). Scope: the F1-F7 fixes, new seal/guard tests, loader preflight, pins and receipts.
Production code, operators, adapters and scoring were cleared in r1 and are not re-reviewed. No SSH, build, native, GPU or movie work; no branch edit.

## Verdict

**CLEAR-conditional.** F1-F3 are fixed and each fix is killed by the new tests when reverted. F4-F7 are fixed or recorded as claimed.
One condition, outside the driver: the loader preflight reports `LDD_MATCH` and exits 0 when a library cannot be hashed (R2-1), so the
parent must either fix it before use or hash the resolved libraries itself. R2-2 to R2-4 are low and need no change before a grant.
This review does not grant launch, merge or adoption; source and science qualification stay separate.

## Findings

| # | Sev | File:line | Finding | Scenario / evidence |
|---|---|---|---|---|
| R2-1 | low (parent admission) | `tools/stageC_ldd_preflight.sh:32` | The per-library `sha256sum` result is never checked (it runs at the end of a pipeline whose status is ignored), so a hash or read failure still prints `LDD_MATCH` and exits 0. The ELF interpreter line (`/lib64/ld-linux…`, no `=>`) is never hashed. | P2: a resolved library that does not exist gives `shasum: … No such file` on stderr, `LDD_MATCH`, rc 0; with `sha256sum` absent, no hash lines at all, `LDD_MATCH`, rc 0. The seal suite's `GOOD` case passes on macOS where `sha256sum` does not exist, so the suite cannot detect this. The `LDD_MATCH` path comparison itself is correct. Fix: check each hash (e.g. loop over an array, `sha256sum "$lib" \|\| exit 16`), hash every absolute path including the interpreter, add a missing-library case. Or the parent hashes the printed paths itself and checks stderr is empty. |
| R2-2 | low (test power) | `tools/test_ccf_dc_stagec_seal.py:256`, `:278` | The real-mode re-hash and the release record are tested by calling `verify_tools()` / `record_release()` directly. Deleting the calls at `ccf_dc_stagec_driver.py:603` and `:799` leaves the seal suite 19/19 OK. | M1, M2 survive (`results/m1_mutants.txt`). The code is correct as read: both calls are present on the real path. The delivery wording "a changed module pin stops a real-mode driver" is shown at function level only. Optional fix: a real-mode `execute()` test with a patched `default_spawner`. |
| R2-3 | low (residual of F2) | `tools/ccf_dc_stagec_driver.py:604` vs `:654` | Fixture inputs and truth are re-hashed before every producer but not between the child's exit and grading, which reads truth from the same directory. | A truth change during a child run is graded unchecked; it is caught by the next job's pre-check (STOP) unless it is on the last job or reverted in between. Optional fix: call `verify_fixture_pinned(tag)` again after the spawner returns. |
| R2-4 | note (F4) | `tools/ccf_dc_stagec_driver.py:115` and `:400` | The release file is read twice: `verify_release` parses one read, `release_bytes` is a second read. | If the file changes between the reads, `release_copy.json` holds unverified bytes. Its sha256 is in `final_status.json`, so the parent can detect this against its own release hash. Optional fix: read once, verify and copy the same bytes. |

## Fixes checked

- **F1** Leases are released only in `execute()`'s final `finally` (`:822`). The new tests probe with fresh descriptors while `pair_report`, `coverage.json`, `final_status.json` and `write_manifest` run, and after an exception in `write_manifest`. Mutants M4 (release at the start of `finish`) and M5 (release before `finish` on Stop) are killed.
- **F2** `verify_fixture_pinned` hashes `MANIFEST.json` against `manifest_sha256` and all 33/26 pinned files before every producer (`:604`). Staged copies are written from the hashed bytes and compared with the pinned `file_hashes`. M3 (no per-job check) is killed by 4 tests (truth, input+manifest together, manifest alone, N job); M7 (no manifest-pin check) is killed by 2.
- **F3** `do_guard` reads, hashes and runs the same bytes with `bash -c` (`$0`=`stageC_guard.sh`; the guard never uses `$0`/`BASH_SOURCE`; 6847 bytes, well under the 128 KiB per-argument limit). M6 (hash check removed) is killed: the sentinel runs.
- **F4** `release_copy.json` (exact bytes, `xb`) is written under the leases; `final_status.json` has sha256, `run_id`, `authorized_by`; the copy is in the manifest (wiring: see R2-2, R2-4).
- **F5** `compgen -A variable STAGEC_TEST_` replaces the pipe. G1 (old `env | grep -q` predicate) is killed by the new large-environment guard test on macOS. Note: `compgen` needs bash built with programmable completion; without it the `|| true` would make the hook check pass. Stock distribution bash has it, and the driver never passes `STAGEC_TEST_*`. `${!STAGEC_TEST_@}` would avoid that dependency.
- **F6** Each receipt has `env_passed`, `env_dropped_names` and `env_policy`; M8 (no `env_passed`) is killed. `proc_identity` runs on the first sample after `Popen` returns (after exec), record-only. The docstring now calls the argv/env comparison a spawner record. Limit: `ldd` shows only DT_NEEDED libraries. `motioncorr_core` links shared `CUDA::cudart` and `CUDA::cufft`, which `ldd` sees, but `libcuda.so.1` is opened by cudart with `dlopen` and is never in `ldd` output, so `LDD_MATCH` says nothing about which driver library a CUDA row loads.
- **F7** `amend1_window/SHA256SUMS`: 12 OK, 1 FAILED (its own line), unchanged. `SHA256SUMS.v2`: 12/12 OK, excludes itself and `AMENDMENT.md`. The driver manifest excludes `SHA256SUMS`.
- **Pins/scope** The five brief hashes and the three test hashes match HEAD. `STAGEC_PINS.json` changes only the guard pin; the module pins match the current files. `PINS.json` stage_c_draft entries match. The r1 archive (`evidence/stageC/review_r1/`, `review/STAGEC_R1_REPORT.md`) is byte-identical to the r1 scratch directory (report `577c14ca…`, manifest `23519dc3…`). `src/ tests/ test-data/` and the reviewed tools are unchanged since `96e7e7be`. The CMake change only registers `CcfDcStageCSeal`. The new files are GPL-2.0-or-later.

## Documented limits (agree; no new policy)

SIGKILL/SIGHUP of the driver leaves no manifest. SIGTERM during sealing can leave a partial seal, though the leases are still released. `do_guard` has no timeout, which fails safe. `gpu_status: OBSERVED` is not proof of the GPU2 UUID. The loader comparison is against the current full environment, not Stage B's environment, which was never recorded. Before a grant the parent still needs the fresh GPU2 0 % baseline (foreign context only), CPU 80-87, the three existing lock inodes, the pinned binary/source/input/loader identity, and the release.

## Results (local macOS, CPython 3.15.1 / NumPy 2.5.4, `OMP_NUM_THREADS=2`)

- Suites at HEAD: guard 9 OK (24 s), seal 19 OK (6 s), lifecycle 12 OK (16 s): `results/suite_*.{out,rc}`. The full 19-test driver suite was not rerun; no new concern needed it.
- Mutants (`scripts/m1_mutants.py`, `results/m1_mutants.txt`, `results/mutant-*.out`): unmutated control OK; M3-M8 and G1 killed; M1, M2 survived.
- Failed attempt kept: `results/attempt1-FAILED-missing-test-data/`. The mutant trees lacked `test-data/`, so every "kill" was an ImportError; the M7 anchor matched twice. The rerun adds the symlink, a control and a BROKEN verdict.
- Preflight probe: `scripts/p2_preflight_hash_failure.sh` → `results/p2_preflight_hash_failure.txt`.
- Static checks (tool diff, module pins, F7 counts, guard size, SPDX, CUDA linkage): `results/p3_static_checks.txt`.
