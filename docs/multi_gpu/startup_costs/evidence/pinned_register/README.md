# Evidence: registered hugepage staging pool alone (#53 step 2)

Design and status: [`../../pinned_stage_register.md`](../../pinned_stage_register.md).

## Revisions

| Arm | Source | Content |
|---|---|---|
| main / base | `116eb04a` | `cudaHostAlloc` staging pool |
| s2 / cand | `9eddaf1f` (`perf/pinned-stage-register`) | `16bd9eee` = `351db93d` without the warm-up, plus `MADV_DONTFORK` and its test |
| c1 (4GPUs only) | `6d9527a9` (`perf/cuda-warmup-thread`) | step 1 alone, for attribution |

## SCARF paired A/B, `scarf/`

- **Venue:** job 3632667 ran exclusively on gn0002 (`ab-3632667.out`). gn0005,
  used for the steps 1+2 A/B, was held by another user's two-day job. gn0002 is
  the same model: 2× EPYC 7302, 4× A100-SXM4-40GB, persistence mode on, THP
  `always`, defrag `madvise`, kernel 5.14.0-687.53.1.el9_8, driver 580.178.04.
- **Builds:** both arms built from scratch in job 3632665 (`build-3632665.out`).
- **Harness:** `warmab.py` is the steps 1+2 harness with only the paths changed.
  It drives `tools/multi_gpu/run_dataset.py` on the 24 tutorial movies, 12 reps,
  alternating order, with one discarded warm-up per arm. Lanes are
  0-7/8-15/16-23/24-31, each on its GPU's NUMA node.

| Config | base median | cand median | Saving | cand faster | Sign test |
|---|---|---|---|---|---|
| 1×8 | 5.669 s | 5.597 s | 72 ms (1.3%) | 8/12 | p=0.39, **not resolved** |
| 4×8 | 4.337 s | 4.256 s | 81 ms (1.9%) | 9/12 | p=0.15, **not resolved** |

**Run order (post hoc, `position.txt`).** At 1×8 the second run of a pair is
about 80 ms faster whichever arm it is:

- base − cand is −0.009 s when cand runs first and +0.159 s when it runs second;
- averaged over consecutive reps, which run the arms in opposite orders, it is
  +0.075 s, with 6/6 pairs favouring cand (p=0.031).

The decision rule fixed beforehand was the plain sign test, so this figure is not
counted. The steps 1+2 run shows the same order pattern
([`../warmup/scarf/position.txt`](../warmup/scarf/position.txt)).

**Products.** `products.txt` uses `cmp_keep.py`, which is `cmp_trees.py`'s rule
on the kept 1×8 merged trees. It normalises each arm's run root, binary path,
the random `.aggregate-XXXXXX` suffix and the worker pid. Result: 24 MRC and 60
other files IDENTICAL. Flipping one MRC payload byte gives DIFFERENT.

**Probes.**
- `probe-pin.jsonl` was recorded in job 3632667 before the A/B, on GPU0, lane
  0-7, 10 fresh processes per method. Pinning 128 MiB took 85.9 ms with
  `cudaHostAlloc`, 15.1 ms registered with huge pages and 59.2 ms registered
  with 4 KiB pages. Release took 33.7, 3.7 and 14.4 ms. See
  [`../pin_summary.txt`](../pin_summary.txt).
- `probe-3632668.out` holds the fork probe. Job 3632667's fork probe hung on a
  bug in the probe itself (one pipe used in both directions) and was killed;
  that is the `Terminated` line in its log. The fixed probe ran in job 3632668 on
  the same node.

## 4GPUs, `4gpus/`

The A100 80GB PCIe was on GPU0 (driver 570.86.10, persistence off), with lane
96-103, kernel 6.8.0-136, THP `madvise`, defrag `madvise` and an uptime of
87.7 days. All builds and scratch were in `/dev/shm/mcs2`. `run_all.sh` ran
three regions under `/tmp/motioncorr-bench.lock`, taking
`/tmp/motioncorr-gpu0-correctness.lock` only for GPU work:

- `region_a.sh`: from-scratch builds of main, s2 and c1 (tests off), the probes,
  then `stall_ab.sh`;
- `region_b.sh`: identity;
- `region_c.sh`: ctest.

**Slow-round series** (`stall_ab.sh`, `analyse.txt`, `runs-stall.tgz`).

- **Runs:** 12 rounds at 24 movies (the kit24 STAR, sha `6d52c471e7ce4b5a`) and
  4 rounds at 96 movies, arms rotating, all 51 runs rc=0.
- **Recorded per run:** every run was profiled. Around each process the
  system-wide `/proc/vmstat` counters (`compact_stall`, `compact_fail`,
  `thp_fault_alloc`, `thp_fault_fallback`, …), free 2 MiB blocks, lane CPU and
  the settle gate were recorded.
- **Host:** load average 1.2-1.7 during the runs; 17,553 free 2 MiB blocks.

| 24 movies, paired over 12 rounds | s2 − main | c1 − main |
|---|---|---|
| process wall | −117 ms (11/12, p=0.006) | −126 ms (12/12) |
| first movie `ingest setup` | −68 ms (12/12): 96.6 → 28.9 ms | 0 |
| outside `run` (mostly exit) | −28 ms (12/12) | +2 ms |
| mid-run excess | −12 ms | −11 ms |

- **Compaction:** `compact_stall` and `thp_fault_fallback` stayed at 0 around
  all 51 runs.
- **THP faults:** each s2 run took 48 THP faults, one per 2 MiB of the 96 MiB
  pool.
- **`ingest setup`:** s2 took 28.1-29.3 ms in all 16 runs.
- **Slow runs:** no run in any arm was more than 500 ms above its arm's median.

**Earlier slow rounds** (2026-10-14, steps 1+2 binary). The profiled
fixed-cost runs are re-read in
[`../warmup/4gpus-fixed/slow_rounds.txt`](../warmup/4gpus-fixed/slow_rounds.txt):

- **Where the time went:** the excess was spent in mid-run movies, not in the
  pool setup. The first movie's `ingest setup` never exceeded 33.6 ms in a steps
  1+2 run.
- **All arms:** mid-run excess above 1 s occurred at 96 movies in 5/8 main runs,
  4/8 c1, 6/8 c2 and 4/8 c3.
- **Largest outlier:** r4_n96_c2 (+5.9 s) slowed every stage of every movie from
  movie 67 onward. A one-time allocation at the first movie cannot do that.
- **Host load:** a load average of 11.5-13.1 during those runs, against 1.2-1.7 now.
- **kit24:** its two slow candidate rounds were unprofiled, so they cannot be
  attributed directly. They are the same size as these mid-run events.

**Probes.**
- `probe-pin.jsonl`: 15 fresh processes per method. Pinning took 112.0 ms with
  `cudaHostAlloc`, 21.9 ms registered with huge pages (21.5-24.2) and 75.3 ms
  registered with 4 KiB pages. Every huge-page acquisition was fully huge, with 0
  compaction stalls.
- `probe-fork.txt` shows the same pattern as SCARF. `fork()` took 8-9 ms with
  `cudaHostAlloc` (shared mapping), 85 ms registered without `MADV_DONTFORK`
  (copied), and 7.5 ms with it (not mapped in the child). No stale pages.

**Identity** (`identity/summary.txt`, s2 binary `5b390ddc8498fc45` vs main
`b956fead76fc2585`):

- **Rows:** eo, eo+noDW, eo+noDW with `MOTIONCORR_FRAME_POOL_POISON=1`,
  `--ingest auto` late binning 1.25, CPU, mixed geometry on GPU and CPU, and
  s2 with `MOTIONCORR_PINNED_REGISTER=0`.
- **Result:** all IDENTICAL, and both controls report DIFFERENT.
- **Path taken:** the candidate log shows the pool grown to 100663296 bytes and
  no fallback line.

**ctest** (`ctest/`):

- **CUDA:** 88/89 (main has 84).
  - The new tests are `CudaPinnedStage` and its four mutants, each detected
    (`pinned_stage_mutants.txt`). The fork mutant fails exactly the fork check.
  - The one failure is `CiFailClosedControls` (test 6, trusted git lookup). It
    fails the same way on main's build of the same staged tree, which has no
    `.git` (`ctest-main-cuda-failed.log`).
  - `MultiGpuScheduling`, `CudaFaultMatrix` and `CudaPreprocessingFailurePaths`
    passed.
- **CUDA=OFF:** 51/52; the same `CiFailClosedControls` failure.

## Limitations

- **Hosts:** SCARF ran on gn0002, not gn0005. The 4GPUs series ran on a quiet
  host, so it shows no stalls under today's conditions; it does not reproduce
  the loaded conditions of 2026-10-14.
- **Fragmentation:** compaction under a shortage of free 2 MiB blocks was not
  tested.
- **What is resolved:** the 4GPUs process-wall gains are characterisation only.
  The SCARF A/B is the deciding measurement, and it is unresolved.
