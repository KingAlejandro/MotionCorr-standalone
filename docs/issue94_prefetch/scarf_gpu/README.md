# Issue #94 — native CUDA prefetch off/on, on dedicated SCARF allocations

> **CORRECTED — see [`../CORRECTIONS.md`](../CORRECTIONS.md).** Four corrections apply to this
> document and are not edited into the tables below, which are kept as originally recorded:
> (1) the "0 of 9" headline is **1 of 9** — series A pair 1 is +5.273 s, prefetch faster, as
> the table in §2 already shows; (2) "72/72 normalized headers" compared only bytes 0-224 and
> has since been re-verified over the **whole file** minus a 19-byte justified timestamp
> whitelist, across all 12 retained pairs; (3) the cpu16 manifest's
> `distinct_physical_cores: 0` / empty `numa_nodes_spanned` are an awk range-parsing bug —
> the real values are 8 cores across NUMA nodes 0 and 1; (4) §4's mechanism is a
> **hypothesis**, not a measurement. The verdict is unchanged.

**Verdict: no measurable benefit, a reproducible +86% host memory cost. Do not promote.**
Prefetch stays opt-in and off by default. This is the negative result the issue asked to be
preserved rather than argued away.

## What was run

Three separate series, each a **dedicated exclusive SCARF Slurm allocation**, under Alex's
28 Sep parallel-GPU authorisation (#96 `issuecomment-5864906904`). No shared-VM resource and
no `/tmp/motioncorr-bench.lock` was taken or queued on: #53 keeps GPU0/1 with CPUs 96-111,
#69 has GPU2 with 112-119, GPU3 stayed free for colleagues.

| job | label | CPU budget actually applied | node | elapsed | state |
|---|---|---|---|---|---|
| 3511120 | — | — | gn3000 | 00:00:10 | FAILED at configure |
| 3511123 | — | — | gn3000 | 00:00:12 | FAILED at configure |
| 3511125 | A | 8 logical / 4 physical cores, NUMA node 0 | gn3000 | 00:15:42 | COMPLETED |
| 3511134 | B | **1 logical CPU** | gn3000 | 00:24:15 | COMPLETED |
| 3511138 | C | 16 logical / 8 physical cores, NUMA nodes 0+1 | gn3000 | 00:14:13 | COMPLETED |

All five allocations are released. Each was `--exclusive`, so each held the **whole 64-CPU,
4×A100 node** even though the work used one GPU and at most 16 CPUs — ~54 minutes of
whole-node occupancy in total. That is a real cost to the facility and is recorded rather than
implied away; exclusivity was taken because timing on a shared host is not defensible.

### Three failures and one mislabel, recorded rather than quietly retried

- **3511120** — `module load` had been piped (`| tail -5`), so it ran in a subshell and the
  `PATH` change was discarded; cmake then found no `nvcc`.
- **3511123** — the login profile exports a `TMPDIR` that does not exist on the node, and
  `${TMPDIR:-/tmp}` keeps a non-empty bad value, so `nvcc` could not write intermediates. Both
  now have preflight checks that release the allocation in seconds.
- **3511134 was submitted as "cpu16" and actually ran on one CPU.** `sbatch --export` splits on
  commas at the top level, so `--export=ALL,MC94_CPUS=0,1,2,3,...` set `MC94_CPUS=0` and
  treated the rest as separate variable names. It is relabelled **series B / cpu1** here. The
  only reason this was caught is that the manifest records the mask **actually applied**
  (`taskset_cpulist`, read back from the run) next to the one requested. A harness that logged
  only the request would have published a 1-CPU run as a 16-CPU run. The CPU list is now passed
  as a positional argument, which sbatch does not split.

## Provenance

| item | value |
|---|---|
| Source | `ab9cd6b9a3ee5c2f0de11a623d849dc921a71448`, staged by `git archive` |
| Cluster | SCARF, account `scd`, partition `gpu`, node `gn3000` (AMD EPYC, **8 NUMA nodes × 8 logical CPUs**) |
| GPU | 1 × A100-SXM4-40GB, `GPU-c6c43d6a-aa2e-af46-022c-aa4a4735638d` (UUID, not ordinal) |
| Toolchain | GCC 13.2.0, CMake 3.27.6, CUDA 12.8.0, FFTW 3.3.10, LibTIFF 4.6.0, libpng 1.6.40, libjpeg-turbo 3.0.1, zlib 1.2.13 |
| Build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80`, built **inside** the allocation |
| Inputs | 24 tutorial movies + `gain.mrc` + `movies.star`, copied into this task's own scratch and verified byte-identical to the source tree before use (`input_sha256.txt`, 26 files) |
| Scratch | `/work4/scd/scarf1415/motioncorr/mc-issue94/`, `pan_quota` unlimited |
| Options | identical in both arms: `--use_own --j 8 --gpu 0 --angpix 0.885 --voltage 200 --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --dose_weighting --save_noDW --grouping_for_ps 3 --ps_size 512 --gainref Movies/gain.mrc`; the prefetch arm adds only `--prefetch` |

Both arms in every series are `taskset`-pinned to the **same** CPU list, so the producer's
reader threads come out of the same budget and are counted rather than treated as free.

## 1. Correctness — exact, in all three series

Run **before** any timing, and the job is written to exit without producing timings if the
arms disagree. In each series, prefetch off vs on over all 24 movies:

```
MRC payloads identical:            72/72
normalized headers identical:      72/72
STAR artifacts identical:          25/25
total pixels compared:             2759049984 bytes
PROBLEMS: none
```

Headers are compared over bytes 0-224; 224-1024 is the MRC label area and carries a wall-clock
timestamp. Every arm of every series: `exit 0`, 72 MRC + 25 STAR outputs, **0 failed movies**,
`decoded = 24`, `inline_loaded = 0`, `failed = 0`, `over_budget_grants = 0`.

## 2. Timing — prefetch was never faster, in any of 9 pairs

Paired, arm order alternating within each pair, order label retained. `delta = off − on`, so
**positive means prefetch faster**.

| series | CPU budget | pair 1 | pair 2 | pair 3 | mean | faster in |
|---|---|---|---|---|---|---|
| A | 8 log / 4 phys | +5.273 | −5.560 | −10.031 | **−3.44 s** on ~103 s (−3.3%) | 1/3 |
| B | 1 logical | −13.685 | −8.384 | −8.383 | **−10.15 s** on ~171 s (−5.9%) | 0/3 |
| C | 16 log / 8 phys | −0.677 | −5.462 | −1.018 | **−2.39 s** on ~100 s (−2.4%) | 0/3 |

Order-corrected effect `E` and positional bias `P` (from `observed = E ± P`): A `E=−3.97, P=+1.59`;
B `E=−9.71, P=−1.33`; C `E=−3.16, P=+2.31`.

**The three series are not combined into one curve** — different CPU budgets and, for B, a
different regime entirely. Within-series scatter is large in A and C (off-arm spread 16.6 s and
11.5 s), so neither resolves a ~3 s effect on its own. What is not ambiguous is the direction:
~~**0 of 9 pairs across all budgets show prefetch faster**~~ — **CORRECTED: 1 of 9.** Series A
pair 1 (+5.273 s) is in prefetch's favour, as the table directly above records; the aggregate
sentence was wrong. See [`../CORRECTIONS.md`](../CORRECTIONS.md) §1. The direction across the
other eight blocks, and the two tightest arms (B's off arm, spread 0.94 s), are unaffected.

## 3. Host memory — the one large, perfectly reproducible effect

Peak RSS of the **owned process tree**, sampled at 200 ms (not one pid, not the node):

Statistic: **peak over time of the sum of `VmRSS` across the owned process tree**, KiB from
`/proc/<pid>/status`, sampled every 200 ms — a sampled maximum and therefore a **lower bound**
on the true peak; resident set, not an allocator trace, not virtual size, not the node, and not
device memory.

| series | prefetch off | prefetch on | delta |
|---|---|---|---|
| A | 2.97 GiB | 5.51 GiB | **+2.55 GiB (+85.9%)** |
| B | 2.97 GiB | 5.51 GiB | **+2.55 GiB (+85.8%)** |
| C | 2.97 GiB | 5.52 GiB | **+2.55 GiB (+85.9%)** |

Within-arm spread is 5-13 MiB across nine runs. Device memory is **unchanged** at 3497 MiB in
every arm — prefetch adds nothing on the GPU, as designed.

### The byte estimate, validated against the real geometry

Reported `budget_bytes = 5468356608` = `3 × 1822785536`. Recomputing the ADR §5 formula for
the tutorial geometry 3710×3838, 24 frames, 8 IO threads:

```
frame_bytes = round_up_to_page(3710*3838*4) = 56958976
estimate    = 24*(56958976+4096) + 8*56958976 = 1822785536      <- exact match
```

And `peak_reserved_bytes == budget_bytes` in every prefetched run: producer-current, queued and
consumer-active were all charged simultaneously, so the pipeline really did run three movies
deep. The declared bound was never exceeded and no override was ever needed.

## 4. Why it does not pay — the overlap witness (**HYPOTHESIS**, see `../CORRECTIONS.md` §4)

The prefetch accounting explains the null directly, and more convincingly than the noisy walls:

| series | `consumer_wait_s` | `producer_queue_blocked_s` | `producer_budget_blocked_s` |
|---|---|---|---|
| A | 0.393 | 86.17 | 0 |
| B | 5.39 | 94.56 | 0 |
| C | 0.337 | 81.10 | 0 |

**Measured:** in the prefetch-ON arm the consumer waited **0.3-5.4 s out of a ~100-180 s run**
while the producer spent 81-95 s blocked on a full queue. These counters exist only in the ON
arm.

**Hypothesis, not established:** that the decode was therefore never what the wall clock was
waiting for in the OFF arm, and that the producer's concurrent CPU use and extra residency cost
at least as much as the hidden decode saves. The OFF arm was never instrumented for decode time
(`TIMING=ON` was not used), and nothing varied contention or residency independently, so this
is an untested explanation for a difference that is inside the noise in two of three series.

## 5. Verdict

**No-go on promotion.** The feature is correct — exact same-backend products across 24 movies
in three independent series — and its bound behaves exactly as designed. But it buys no
measurable full-run time on any of three CPU budgets and costs +86% host RSS every time. Per
the issue's own stop rule, the negative result is the deliverable: keep `--prefetch` opt-in and
off by default, and do not build further on it without a workload where the consumer actually
waits for input.

## 6. Explicitly UNRUN

- **The composed PR103 / PR110 integrity work.** Composing another task's branch here would be
  a merge this task is not authorised to make, and the standing instruction is that
  reader/error integration with PR110/103/105 is a later bounded composition.
- Multi-worker (2/3/4 concurrent process) schedules.
- EER and compressed-MRC inputs through the prefetch path — routed to the in-line loader by
  design, and still **unrun** rather than supported.
- Any CPU budget wider than 16 logical CPUs, and any NUMA memory pinning. Series C spans two
  NUMA nodes with `membind` unrestricted; no memory-locality claim is made.
- A sample size that could resolve a ~3 s effect. n=3 per series is a screen; ~~0/9~~
  **1/9** pairs favouring prefetch (CORRECTED, see `../CORRECTIONS.md` §1) is a direction, not
  a confidence interval.
- `nsys` transfer-byte counts and per-stage `TIMING=ON` timers, which would resolve finer
  effects than process wall.

### Co-tenancy note

Series B overlapped another MotionCorr task's job (`pr110-native-b`, 3511135) on a **different**
node, gn3001, for roughly its first six minutes. My node was exclusive, so host CPU, PCIe and
GPU were not shared, but `/work4` is a shared parallel filesystem. Series B's absolute walls
should not be compared across series for that reason as well as the CPU-budget difference.
