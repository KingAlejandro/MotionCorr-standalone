# 4GPUs recovery receipts and resource proposal (read-only; recorded 2026-10-26 22:06-22:09 UTC)

Access: strict direct SSH (`BatchMode=yes`, `StrictHostKeyChecking=yes`) to `4GPUs` (`4-gpu-vm`), after the parent restored it at 22:04Z. Only files and metadata were read (remote `tar` of small logs, `ls`, `ps`, `nvidia-smi` queries, `/proc/locks`, `du`). No lock was acquired, nothing was built, tested or launched, no image payload was opened. The host was never down: `up 98 days, boot 2026-07-20`.

## 1. Receipt ledger

| Attempt | Source | Archive sha256 | Start / end (UTC) | Result | Evidence |
|---|---|---|---|---|---|
| 1 | `b75039a0` | `6ce0601b...` | 17:02:28 / 17:16:27 | configure/build rc 0 in `def`, `exp`, `iso`; ctest rc 8 in all three: `CcfDcRequest` failed in `def` and `exp` (empty-argv registration bug), `SyntheticRegression` failed in `iso` (by design). Oracle G1-G6 and all mutants Passed in `exp`/`iso`. | `evidence/venue_attempt1/` (retained, unchanged) |
| 2 | `94e39570` | `c1a27626...` | 17:39:09 / 17:53:17 | configure/build rc 0 and ctest rc 0 in all three builds. | `evidence/venue_attempt2/` (fetched now; `SHA256SUMS`) |
| 3 | `96e7e7be` | `313f671f...` (prepared locally) | never started | host unreachable; the prepared job was stopped; nothing staged. UNRUN. | `evidence/venue_unreachable_20261026.md` |

Attempt 2 details (from `chain.out`, `ctest-*.log`): leases `motioncorr-dcnative-gpu2-cpu80-87`, `motioncorr-cuda-boundary-cpu80-87`, `motioncorr-gpu2-correctness`, `motioncorr-build` acquired 17:39:09Z; all four GPUs idle at admission (1 MiB, no compute apps); affinity CPUs 80-87 (`nproc` 8); `CUDA_VISIBLE_DEVICES` = GPU2 UUID `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`; CMake 3.28.3, nvcc 12.8.61, gcc 13.3.0; interpreter `/home/alex/.mc-venv/bin/python3` = CPython 3.12.3 with NumPy 2.5.3. Release, `-DCMAKE_CUDA_ARCHITECTURES=80`, `-j8`. Source archive sha256 `c1a276265e0af07e18d84cc10896c0b98be514a6f0839c95526b024cc7a65a0e`; build-log hashes in `build-logs-and-archive.sha256`.

| Build | Binary sha256 (`motioncorr`) | ctest totals (selection regex, no `-V`) | CcfDc tests | Skips |
|---|---|---|---|---|
| `def` | `2db45b2df8241e14bda28e9dbe3d7eae0ce9f5612a7b775bc33990aeb27bed6a` | 37/37 passed, 32.7 s real | `CcfDcRequest`, `CcfDcRequestWrongKind_def_told_experiment`, `CcfDcTapField`, `CcfDcRowsPure` Passed | none reported |
| `exp` | `b918cadc571eb09d753fd454a20554400ea6443b6b0738e14670f96c7afb2857` | 47/47 passed, 75.6 s | `ExperimentCcfDcStage` + 7 mutants (3 CPU, 4 CUDA), `CcfDcRequest`, two `WrongKind`, `CcfDcTapField`, `CcfDcRowsPure`, `CcfDcRowsNative` Passed | none reported |
| `iso` | `3a7d4f472c0f795f6e3d7fdb7c31ab5c3e6bdef00ccf95d08a5cf5855155d0ff` | 51/51 passed, 122.9 s (`SyntheticRegression` excluded by the selection) | oracle + 12 mutants (adds 2 CPU-iso, 2 CUDA-iso, key), the same request/tap/rows tests with `--iso` Passed | none reported |

Each build also ran 16 CUDA `hardware`-labelled tests (22-23 s of process time), and the CUDA mutants (`cuda_single_restore`, `cuda_batched_restore`, `cuda_single_resident`, `cuda_single_stage_swap`, and the iso CUDA mutants) were each rejected, which can only happen if the CUDA branches ran on the device. Limit: attempt 2 ran `ctest` without `-V`, so the oracle's own G1-G6 counts, a per-path "eligible > 0" table, an `nvidia-smi` PID witness, the fixture hashes and the exact stdout were not captured.

## 2. What attempt 2 validly covers for the final source `96e7e7be`

`git diff 94e39570 96e7e7be -- src tests CMakeLists.txt test-data` is empty; outside `docs/` only `tools/ccf_dc_native_rows.py` and `tools/test_ccf_dc_native_rows.py` differ. So for `96e7e7be` the builds, binaries, oracle G1-G6, all mutants, `CcfDcRequest`, the `WrongKind` controls, `CcfDcTapField` and the 16 CUDA hardware tests have the same inputs as attempt 2, and the attempt-2 binaries are binaries of that source. Not covered for `96e7e7be`: `CcfDcRowsPure` and `CcfDcRowsNative`, whose Python files changed after attempt 2 (they passed at `94e39570` only), and the capture gaps listed above.

## 3. Fresh occupancy (22:07:52Z)

- GPUs: GPU0 `GPU-eddb42fe-...` 1551 MiB 0 %; GPU1 `GPU-cd5b9f86-...` 425 MiB 0 %; GPU2 `GPU-063e5232-...` 425 MiB 0 %; GPU3 `GPU-b2cb2c39-...` 49769 MiB 86 % (67 C). One compute process holds a context on all four: PID 3983855, user `dvi41342`, `llama-server` (Qwythos-9B BF16), started about 3.6 h earlier, about 1.6 CPUs, affinity 0-123 (unpinned). It was not signalled or inspected beyond `ps`. Not ours.
- CPU: load average 3.3. Over 3 s the busy cores were 7, 1, 105 and 74 (that llama-server and short `pgrep` probes from other sessions); cores 80-87 idle. Memory 432 GiB, 417 GiB available (page cache). Scratch: 592 GiB free on `/`; my two attempt directories use 1.8 GiB. THP `madvise`.
- Locks: none of the 54 `/tmp/*.lock` files is held (checked through `/proc/locks`, no acquisition); no deleted-lock descriptor; the only advisory-lock holders are `cron` and the GitHub Actions runner listener, neither on a MotionCorr lock. My four attempt-2 leases were released when the chain ended. Other sessions on the host: 3 logins.

This is an inventory, not an allocation.

## 4. Remaining qualification needs for final source `96e7e7be` (none started)

1. `CcfDcRowsPure` and `CcfDcRowsNative` passing on the venue at `96e7e7be` (CPU only, using the attempt-2 `exp` and `iso` binaries, which are source-identical).
2. A recorded device-branch witness: the oracle run directly with `--json`, `nvidia-smi` compute-app sampling during the run, the per-path "eligible frames > 0" check for `cuda_single_global`, `cuda_single_local`, `cuda_batched_local`, and full stdout; plus the K267/N fixture MANIFEST hashes regenerated with the venue interpreter.
3. Parent pins: source SHA, the three binary hashes above (or a rebuild decision), GPU UUID, K267 and N fixture hashes, commands (`k267_argv`, `n_argv`, thread pins).
4. Then the tiny tiers, nothing before the parent's admission: CPU-backend rows (K 48 + N 32 = 80 jobs, no GPU) and CUDA-backend rows (K 48 + N 32 = 80 jobs); `M` stays held. All rows run seconds at 128x96.

## 5. Resource proposal (for the parent's admission; correctness only, no timing or performance claim)

- Lane: 4GPUs, CPUs 80-87 under whole-command `taskset`, one job at a time, the same four leases plus a fresh lease name per attempt, fresh occupancy check inside the lease; scratch under a new directory below 5 GiB.
- Stage A, no GPU (`CUDA_VISIBLE_DEVICES=""`): item 1 above, a few minutes.
- Stage B, one GPU: item 2, about 10 s of device time and under 2 GiB of device memory. Propose GPU2 by UUID (or GPU1); GPU3 is unsuitable (86 % utilised by a foreign process, 49.8 GB). Every GPU carries a foreign context, so a GPU grant is needed from the parent; the job would coexist with that context and does not interrupt it. The sampler records the foreign process's presence and utilisation so any coexistence is visible; no timing claim is made from these runs.
- Stage C, after the parent's pins and admission: CPU-backend tiny rows first (no GPU), then the CUDA-backend rows on the same granted GPU.
- `cpu64` is not used (owned by the full-width PR290 work).
