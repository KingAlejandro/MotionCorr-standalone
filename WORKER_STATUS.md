# WORKER_STATUS — issue #26

| field | value |
| :-- | :-- |
| Issue | [#26](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26) — current-main CPU/CUDA operating envelope |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort |
| Task class | measurement |
| Phase | measurement-integrity follow-up applied after the PR109 results review; no reruns |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (= `origin/main` at start) |
| Branch | `round96/26-claude-opus-5` |
| Head | see `git rev-parse HEAD` on `round96/26-claude-opus-5` |
| Draft PR | [#109](https://github.com/KingAlejandro/MotionCorr-standalone/pull/109) |

## Scope

Owns the one shared operating-envelope study and this round's initial GPU benchmark slot.
Contract is `agents/designs/issue_26_operating_envelope.md`. No file under `src/` is touched.

## Changed files

| Path | Kind |
| :-- | :-- |
| `agents/designs/issue_26_operating_envelope.md` | measurement ADR and whitelist |
| `tools/envelope_runner.py` | measurement runner |
| `WORKER_STATUS.md` | this file |
| `tools/test_envelope_report.py` | controls for the product verdict |
| `tools/test_envelope_interference.py` | controls for the interference witness (Linux only) |
| `docs/operating_envelope_issue26.md` | report and operating guide |
| `docs/benchmark_logs/issue26_envelope_2026-09-27/` | raw per-run records |

## Allocation held

| Resource | State |
| :-- | :-- |
| `4-gpu-vm` `/tmp/motioncorr-bench.lock` | **released** 2026-09-28 ~02:45Z; all 4 GPUs idle. Announced on #66 and to #53/#69/#94 |
| `4-gpu-vm` CPUs | `taskset -c 96-111` (16 logical, all NUMA node 1), verified inherited |
| `4-gpu-vm` GPUs | GPU 0 only (`GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`); 1/2/3 left free |
| `cpu64` `/tmp/motioncorr-issue96-cpu-measure.lock` | **released** |
| `cpu64` CPUs | `taskset -c 0-31` (= NUMA node 0). Lane 32-63 untouched and free for other workers |
| `cpu64` validation lock | **not** held; no whole-host run is planned |

GPU is free. #53, #69 and #94 have published NEEDS_GPU; #72, #95 and #99 need none.
Scheduling note offered on #66: #94 produces numbers so it needs the lock *and* a settle
gate, while #53 and #69 are correctness-only and need the lock but not a settle gate, so
they can run back to back. Assignment is Codex monitoring's call, not mine.

64 GB of timed outputs are retained under `/home/alex/MotionCorr-issue26-envelope/results/`
(host has 700 GB free). Per-product digests are committed, so those trees can be pruned.

## Builds (frozen, Release)

| Build | Host | Binary `sha256` | Flags |
| :-- | :-- | :-- | :-- |
| `build-cuda` | 4-gpu-vm | `d80cdadb9c6c5e12020dcd7dba955b3758803f6aaa51456b8d2b935f6a89789d` | `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, `sm_80`, `TIMING=OFF` |
| `build-cuda-timing` | 4-gpu-vm | `22e59177ee0b3b3da27bedd0a80318b0741e1d67c742cc2e5b6a3534cc9c28dd` | as above, `TIMING=ON` |
| `build-cpu` / `build-cpu-timing` | cpu64 | recorded in `evidence/build/` | `-O3 -DNDEBUG`, `CUDA=OFF` |

gcc 13.3.0, CUDA 12.8.61, driver 570.86.10, FFTW 3.3.10, libtiff 6.0.1.
Source archive `6d5de8340ad9469c0572767b3af7853ab4fcec030f9286870f507b6db4fe966d`, 650 files,
tree digest `787a3061e3fde06446884c405e48192c387dc5d284f4712c0b735c31185b4ba0`.

## Fixtures (verified against `docs/reference_gates.md`)

- 24-movie STAR `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`
- gain `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`
- movie 00021 `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`
- declared 4-movie screening subset `ed74c9ed3fafdc64fa510265798bc864b1ba36b59730be4a6f9ebda1e3dc09f1`
  (00021, 00029, 00042, 00049) — **byte-identical STAR on both hosts**

## Instrument corrections (round 2)

An independent read-only review found four witnesses that could not observe what they
asserted. All four were verified against retained artifacts or a control before being
accepted, and two changed results, so the GPU series is being **re-run** on the repaired
instrument rather than reported with caveats. Fixed in `24ea368`:

1. `TIMING` stage intervals were never captured — the profiled build writes them to stdout,
   not the per-movie log, so the profiled arm added nothing. The loose parse also promoted
   prose ("Frames to be used: 1 2 3 …") into the interval record as a 1.0-second stage.
2. The CUDA witness was a startup banner that survives every movie falling back to the CPU.
   Re-checked against the retained Phase 0 run: 24/24 movies carry per-movie CUDA execution
   evidence and no log contains a fallback warning, so the published numbers stand.
3. Interference used `ps pcpu`, a lifetime average that cannot resolve activity during a run;
   and ownership was a walked `ps` snapshot that raced with the sampler's own children,
   recording `foreign_cpu_max = 2750%` against its own `ps` and MotionCorr's own `gs`. Now
   `/proc` utime+stime deltas with session-id ownership, with a three-way control.
4. Process wall from `/usr/bin/time` was never parsed (colon inside `(h:mm:ss or m:ss)`).

The cpu64 series is being allowed to finish on the earlier instrument: its conclusion is a
paired unbound-versus-bound contrast in one lane, where self-contamination is identical in
both arms and cancels. Its interference figures will be labelled as instrument v1.

## Latest results

- Phase 0 baseline, 24 movies, `--use_own --gpu 0 --j 8`, 5x5 patches, dose weighting:
  **29.03 s**, exit 0, 109 products, 2.66 of 16 cores, 1.52 GiB peak RSS, 3134 MiB traced
  device peak.
- Phase 1 screen, 10 distinct effective treatments x 3 repeats: wall time is a function of
  the effective IO-thread count alone. Across `--j` in {1,2,4,8} at IO=1 the spread is 0.8%,
  below the 2.5-8.4% run-to-run spread. 12/12 arms bit-equal, no failures.
- Phase 1 confirmation, all 24 movies, paired with order alternating: `j16/io16` beat
  `j8/io8` in 5/5 pairs, order-corrected effect **1.889 s** on ~30 s; `j16/io8` was slower
  than `j16/io16` in 3/3 pairs by **3.376 s**. More IO threads help; more compute threads at
  fixed IO do not.
- `TIMING` breakdown, 24 movies: `read movie` 7.082 s is the largest stage; host input and
  output total ~13.8 s against ~4.0 s of GPU-accelerated arithmetic.
- cpu64, rep 1: `j=32` 25.15 s unbound vs 18.93 s with `OMP_PROC_BIND=spread`.
- All controls pass: `tools/test_envelope_report.py`, and
  `tools/test_envelope_interference.py` on the Linux host.

## Blockers

None open. Two cleared, one raised for someone else.

**Raised (not attributed):** the `cpu64` 0-31 lane was **not exclusive** during the series.
The retained record shows, at the worst single sample of arm `c1_j2_spread` (70 samples),
**63 foreign threads in total** with a last-run CPU inside the lane, and an **unidentified
Python workload** as the dominant in-mask command label across that arm, ahead of `ctffind`.

Precision limits on that statement: 63 is the aggregate over all commands at one sample, not
any one command's count; `foreign_in_mask_by_command` values are accumulated thread-sample
hits, not simultaneous threads; and **no per-sample series, PID, session id or command line
was retained**, so per-command simultaneity is not recoverable and the workload is **not
attributed to any task**. These arms used instrument v1, whose in-mask metric counts sleeping
threads on a lifetime-average filter and is **not comparable** to the repaired GPU figure.
Nothing was altered. Full statement in `docs/operating_envelope_issue26.md` §6.3.

## Corrections applied after the PR109 results review (head `fca95d76`)

Three published claims withdrawn, each verified before acting, each fixed with a negative
control that has a non-vacuous half. No GPU work rerun; no retained record edited.

| withdrawn | cause | now |
| :-- | :-- | :-- |
| 3134.34 MiB "allocator-traced peak"; "gap is CUDA context"; device worker-sizing rule | parser summed 26 per-call size-accounting values (25x62.59 + 1569.59); the value is not a trace either | parser withholds `sum` for size-like tags; **no per-process device bound claimed** |
| "1.43 GB of 1.45 GB, 98.6% node-local" | witness sampled the `taskset`/`time` launcher, and `numastat` units are MB | payload resolved via `/proc/<pid>/exe`; residency in bytes from `numa_maps`; **no NUMA claim** |
| CPU binding "resolved at j=4, 8, 16" | `±2 sem` read as significance; t factor is 4.303 at n=3 | descriptive 95% t CI; resolved at **j=8, 16 only**, provisional |

Also: fixed-`j8` IO speedup is **1.959x** not 1.90x; "`--j` only matters via I/O" withdrawn
as too universal. Cancellation now terminates the owned process group; settle failures are
**quarantined**. Two `/proc` field-index bugs fixed (session read as pgrp, starttime as
field 21). New controls in `tools/test_envelope_runner.py`, run CPU-only on cpu64 cores
32-63 under the validation lock with `ctffind` recorded and untouched.

## Verified gates

| gate | scope | result |
| :-- | :-- | :-- |
| payload + core header + masked MRC labels + STAR + EPS | 12 GPU screen arms, 3 GPU confirmation arms, 12 cpu64 arms | **all EQUAL**, 0 differing |
| effective `--j` / IO cap read back from the binary's own logs | every arm | **matches request** on all |
| per-movie CUDA execution witness | every GPU arm | **24/24 movies**, zero fallback warnings |
| cross-pass determinism, two passes hours apart | 13 arms | **bit-identical payloads 13/13** |
| non-zero exits | 98 timed arms | **none** |
| `tools/test_envelope_report.py` | product verdict, 4 cases | **pass** |
| `tools/test_envelope_interference.py` | interference witness, 3 cases | **pass** on Linux host |

## Explicit unrun cases

Phase 2 worker execution (protocol only; #53 owns workers). Multi-GPU and scaled-resource
series. Phase 3 workload shape — frame counts, geometry, formats, heterogeneous costs. Cold
cache and networked storage. A clean-lane CPU re-measurement, which §6.3 says is needed
before any CPU `--j` recommendation is load-bearing.

## Next step

None outstanding. Draft PR #109 carries the corrections. Unrun and stated: payload
NUMA/memory re-measurement, controlled-lane CPU rerun, the 1/2-worker matrix against PR106,
Phase 2 multi-GPU, Phase 3 geometry/frame counts. Each needs a slot this task does not hold.
