# Stage C driver review r1 (Opus, read-only)

Target: PR289 worktree `t3-9c391c37`, HEAD `26e74d8a20e5147d9f5aa11c09f51bbd69783c93` (clean), code bytes fixed at `72f4b7d9`.
Scope: Stage C driver, guard, tests, pins and amendment-1 evidence. No SSH, build, native, GPU or movie work. No branch edit.

## Verdict

**Not CLEAR at driver `daee5f14…`.** Three small code findings (F1–F3) contradict amendment 1 or the "rehash before each job"
requirement. None touches scoring, operators, argv or production code. After F1–F3 are fixed, re-pinned and the
driver/lifecycle suites rerun, the result is **CLEAR-conditional** on the parent's fresh resource, source, binary and release
admission. F4–F7 are low and can be fixed in the same pass or recorded. Launch is not authorised by this review.

## Findings

| # | Sev | File:line | Finding | Scenario / evidence |
|---|---|---|---|---|
| F1 | medium | `tools/ccf_dc_stagec_driver.py:687` | `finish()` releases the three leases first, then writes pairs/coverage/final status and the manifest. Amendment 1 §2 says the manifest is written "and only then releases the leases". | P1: all three lock files are acquirable from another fd while `write_manifest` runs. The child is already dead, so no product contamination, but another lease holder can start on GPU2/CPU 80-87 while the driver is still hashing. The SIGTERM lifecycle test only checks the leases are free after `execute()` returns, so it cannot see the order. Fix: release in a `finally` after `write_manifest`. |
| F2 | medium | `tools/ccf_dc_stagec_driver.py:533-537` | The per-job input check compares the staged `.star`/`.mrcs` with the fixture `MANIFEST.json` re-read from disk, not with the pinned `file_hashes`. Truth files the grader reads from the same directory are not re-hashed per job. | P2b: after `verify()`, `affine.star` and its manifest entry are changed together; 2 jobs run with `TAMPERED` staged input and no stop. Control P2a (input only) stops with "input affine.star changed". Fix: compare with `self.pins["fixtures"][tag]["file_hashes"]`; re-hashing all 59 pinned fixture files per job is cheap. |
| F3 | medium-low | `tools/ccf_dc_stagec_driver.py:462` (hash only at `:398`) | The guard script is hashed once in `verify()` and then re-read by `bash` before every job without a hash check. | P3: guard replaced after job 1; job 2's guard log is `UNPINNED-GUARD-RAN` and its rc gates the campaign. A replaced guard that exits 0 would pass silently. Fix: re-hash before each `bash` call, or run the pinned bytes from a private copy. |
| F4 | low | `tools/ccf_dc_stagec_driver.py:371`, `:703-706` | The release is verified but never recorded: no release sha256, `run_id` or `authorized_by` in `final_status.json`, receipts or the manifest. | The bundle cannot show which release authorised it. Fix: copy the release file into the outdir (hashed) and put its sha256 and `run_id` in `final_status.json`. |
| F5 | low | `tools/stageC_guard.sh:19-20` | `env \| grep -q '^STAGEC_TEST_'` under `set -o pipefail`: when grep exits on its first match while `env` is still writing, `env` gets SIGPIPE, the pipeline returns 141 and the hook reads as absent. | P4: `STAGEC_REAL=1 STAGEC_TEST_NO_SLEEP=1` plus a 300 kB variable: hook check passed 20/20 (rc 15 at the next check); with a small env it is rejected 20/20 (rc 20). The driver path is not affected: `do_guard` passes only `ENV_ALLOW` plus non-test `STAGEC_*`, and `run` refuses `STAGEC_TEST_*` itself. This affects standalone guard runs only. Fix: `env \| grep '^STAGEC_TEST_' >/dev/null`. |
| F6 | low | `tools/ccf_dc_stagec_driver.py:352`, `:566-573` | `default_spawner` returns `list(argv), dict(env)`, i.e. its own inputs, so the "executed command or environment differs" check cannot fail on the real path; only test spawners exercise it. The values of the inherited `ENV_ALLOW` variables (PATH, HOME, LANG, LC_*, TMPDIR, USER, LOGNAME) are not recorded. `LD_LIBRARY_PATH` is dropped, whereas the retained/Stage B producer calls used `{**os.environ, **env}` (`tools/test_ccf_dc_native_rows.py:273`). | A missing library would give rc 127 on the first B4 row (a STOP, so it fails closed). A silently different cuFFT on CUDA rows would not be caught, because C-REPRO is CPU-only. Fix: record the full child env in the receipt and read `/proc/<pid>/cmdline`, `environ` and `exe` in the first sample. Parent admission: `ldd` of the three binaries under the scrubbed env matches the Stage B resolution. |
| F7 | low (evidence) | `evidence/stageC/amend1_window/SHA256SUMS` | The manifest lists itself; `shasum -c` gives 12 OK and 1 FAILED (`./SHA256SUMS`). This is the same class as the Stage A/B `chain.out` amendment. The driver's own `write_manifest` excludes SHA256SUMS correctly. | Fix: add a note or a v2 manifest without the self line. The other 12 lines verify. |

Notes, no change required:
- `do_guard` has no timeout (`:462`): a hung `nvidia-smi` holds the leases indefinitely. No job runs, so this fails safe.
- On timeout the driver records a synthetic rc 124 (`:344`), not the signal status, and the receipt has no explicit timeout flag. The row still stops as FAILED_RUN.
- `gpu_status: OBSERVED` means a tree pid was listed by nvidia-smi, not that it was on GPU2. In P7 a pid on GPU3 is recorded OBSERVED. The amendment makes this record-only, so the parent must check UUID equality when reporting. In the query-error case the message says "no tree pid listed" (`read_errors` does count it).
- `acquire()` uses `O_CREAT` (`:439`): a deleted foreign lock file would be recreated as a new inode and split the flock (same behaviour as Stage A/B `exec >>`). The parent's fresh check should confirm the three lock inodes exist.
- Limits on the driver's own death: SIGKILL/SIGHUP of the driver leaves no manifest. PDEATHSIG covers the direct child only, and the kernel drops the flocks. SIGTERM during `finish()` can also leave no manifest. Shared libraries are not pinned; compiler provenance is recorded only.

## Checked and OK

- Pins: all six brief hashes match HEAD. `PINS.json` stage_c_draft entries match. Production `src/ tests/ test-data/` and the reviewed tools (`ccf_dc_native_rows`, `ccf_dc_tap_field`, `check_*`, `motion_field`) are identical to `96e7e7be`. The CMake diff only registers tests. New files are GPL-2.0-or-later and use only stdlib + NumPy (ctypes is stdlib).
- Plan (P0, real pinned ledger): phases 12/80/68, with B4 = affine/pedestal/noisy CUDA `exp` none/global/local/both first. 96 pairs, every pair the same case and tier. The 16 repro rows are exactly the CPU N arm-none rows (8 `exp` production, 8 `iso` isotropic). B3 triples complete 16/16, with no duplicate (case, backend, binary, arm) key.
- Commands use the unchanged `k267_argv`/`n_argv`/`run_env`. CPU rows hide the GPU (`CUDA_VISIBLE_DEVICES=""`, `NVIDIA_VISIBLE_DEVICES=void`). CUDA rows get the GPU2 UUID, `PCI_BUS_ID` and `--gpu 0`. OMP is 8/2. Inherited variables are scrubbed to `ENV_ALLOW`.
- Gates: `check_row` needs SCORED, finite values, runtime SCORED, witness VALID, the declared coverage and strictly positive eligible counters at the declared sites. Local must be zero where it is not requested. The unchanged grader enforces exit 0, complete publication, no runtime-to-STAR rescue, selectivity on every reached site (including `cuda_single.local`) and the backend-fallback ban. rc != 0 stops. B3 goes through the real `identity_report`. C-REPRO uses a fixed 1e-5 plus verdict equality and stops the weight set only. Science FAIL/UNIDENTIFIABLE rows continue.
- Binary sha256 is re-hashed before every job (`:529`). The manifest excludes itself and has a closure re-hash. Events are written open-write-close. Every run dir is new, with no retry.
- Release refusals: driver/pins/ledger/source/outdir binding, `test_fixture` false, `authorized_by`, `run_id`. A real run refuses hooks, fake pins and `STAGEC_TEST_*`.
- Guard fails closed: authors' 8/8 pass locally (macOS). Reviewer mutants are all killed by the suite (5/5): other-app stop removed, utilisation range removed, df headroom removed, `run` swallowing failures, `free` unchecked. Checks confirmed: exact UUID exactly once, numeric memory/utilisation, all 8 cores with a positive delta, df/du/free numeric, 20 GiB cap.
- Lifecycle 12/12 locally (macOS, UNOBSERVED branch). On Linux, `test_sampling_records_a_child_and_its_descendant` asserts OBSERVED and cannot pass with UNOBSERVED. The venue log shows 12 OK.
- CUDA pid→UUID sampler (P7, fake nvidia-smi): maps only tree pids, the foreign pid is excluded, rc != 0 is an error, and an unmapped run is UNOBSERVED. Nothing is fabricated.
- Venue window: `logs/hashes.txt` matches the pinned guard/driver/test hashes. Guard rc 0, GPU2 425 MiB at 0 %, only PID 3983855 (llama-server) on it, cores 80-87 at 0 %. Guard tests 8 OK and lifecycle 12 OK on Linux.

## Not run

The full 19-test driver suite (about 4 min) was not rerun; the probes use its `World` harness. No real producer, GPU, guard on the venue, or binary check.

## Reproduce

Interpreter: `/tmp/mc-dc-venv/bin/python3` (CPython 3.15.1, NumPy 2.5.4; the venue pins 3.12.3/2.5.3). `OMP_NUM_THREADS=2`, `TMPDIR` under this directory, `PYTHONDONTWRITEBYTECODE=1`. Each script takes the worktree path as its first argument.
- `scripts/p0_ledger_structure.py` → `results/p0_ledger_structure.txt`
- `scripts/p1_p3_driver_probes.py` → `results/p1_p3_driver_probes.json` (P1, P2a/P2b, P3, P5), rc 0
- `scripts/p4_guard_pipefail_hook_check.sh <guard>` → `results/p4_guard_pipefail_hook_check.txt`
- `scripts/p6_guard_mutants.sh <wt> <py> <results>` → `results/p6_guard_mutants.txt`, `results/mutant-*.out`
- `scripts/p7_gpu_map_shim.py` → `results/p7_gpu_map_shim.json`
- Authors' suites: `results/guard_tests.{out,rc}` (8 OK), `results/lifecycle_tests.{out,rc}` (12 OK)
- An earlier probe attempt failed with rc 127 (`timeout` is not on macOS) and was rerun without it. The first P0 attempt used a Python without NumPy.
