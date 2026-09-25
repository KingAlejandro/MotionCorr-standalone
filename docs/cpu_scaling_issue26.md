# Issue #26: CPU strong scaling — measured causes, refuted causes, and one fix

This document records a measurement-led audit of
[Issue #26](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26)
("Diagnose CPU parallel scaling bottlenecks and sub-linear multi-threading
efficiency") and the one code change the evidence supports.

Everything below was measured on **cpu64** (`small-refmac-machine`). No CPU-only
MotionCorr workload was run on the shared GPU host.

---

## 1. Provenance

| Item | Value |
| :-- | :-- |
| Source commit | `3e3a19679337d3de61327c02eef1a2947cf13517` (`origin/main`) |
| Host | `small-refmac-machine` (ssh alias `cpu64`) |
| CPU | AMD EPYC 7763, 64 vCPU, 2 sockets x 32 cores, **1 thread/core as seen by the guest**, 2 NUMA nodes (0-31, 32-63) |
| Memory | 226 GiB |
| Virtualisation | KVM guest; `cpu MHz` pinned at 2445.406 (nominal TSC, not a real frequency reading); no `cpufreq` interface |
| Compiler | `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` |
| CMake | 3.31.x from `~/.mc-venv` (cpu64 has no system cmake) |
| FFTW | 3.3.10 (`libfftw3`, `libfftw3f`), system packages |
| Build flags (baseline + candidate) | `-O3 -DNDEBUG -std=gnu++17 -fopenmp` (`-DCMAKE_BUILD_TYPE=Release`) |
| Stage-timer build adds | `-DTIMING` |
| Baseline binary | `build-rel/motioncorr` sha256 `13d501afd518a7a96aa1556dfb5c5b434ae768617d7ddfe28f463d059192e13d` |
| Baseline `-DTIMING` binary | sha256 `3a669ef89e277592fcf944114b51d0848a17d7648964b5d88f4fade88ef6653d` |
| Candidate binary | `build-rel/motioncorr` sha256 `cf866dce200766a262d053073b0e64bb94c96f5467851a880f577cc8a3fac01e` |
| Candidate `-DTIMING` binary | sha256 `3948c80eda248296879c9f2e6c9a5dce27efbdeb137c951a4febbacb65bfec4d` |
| Movie | `20170629_00021_frameImage.tiff` sha256 `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0` |
| Gain | `gain.mrc` sha256 `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1` |
| Movie geometry | X=3710 Y=3838 N=24, padded to 3888 x 3888; `Fframes` are 1945 x 3888 complex |

Command under test (the exact form used to produce Issue #26's numbers,
recovered from `tools/benchmark_cpu_profile.py` on the reference host):

```
motioncorr --i movies1.star --o <out> --use_own --j <N> --dose_weighting \
           --dose_per_frame 1.277 --patch_x <P> --patch_y <P> --bfactor 150 \
           --gainref Movies/gain.mrc --do_at_most 1
```

### Measurement hygiene

Timed runs were serialised box-wide with `flock /tmp/motioncorr-cpu64-bench.lock`
(builds included — a build that lands mid-series invalidates it), gated after
acquisition on `load1` and on `pgrep -x` for compiler process names, and each run
logged third-party CPU once per second so contention is in the record rather than
assumed away. Two `ctffind` processes belonging to another user held ~2 of 64
cores continuously throughout; that is a constant across all arms but is recorded
per run rather than treated as negligible.

`perf` is not usable here: the box has no `linux-tools`, it is a KVM guest (PMU
counters are not virtualised), and `kernel.perf_event_paranoid` is set to `4` by
whoever administers this shared machine. Lowering that is a security-relevant
change to someone else's system, so Phases 1 and 2 of Issue #26's proposed
methodology were **not** performed as written. They were replaced by direct
in-binary instrumentation and by ablation against controls, which attribute cost
causally rather than by correlation. This is a real deviation from the issue's
plan and is called out as such.

---

## 2. Claim-by-claim audit

### Claim 1 — "Serialized lock contention on FFTW plan creation" (issue's P1)

**Mechanism: confirmed. Magnitude: refuted.**

The mechanism is real and correctly described: `NewFFT::FloatPlan` /
`DoublePlan` take `#pragma omp critical(FourierTransformer_fftw_plan)` in the
constructor (`src/jaz/single_particle/new_ft.cpp:364,405,446,488`) and again in
`~Plan` (`src/jaz/single_particle/new_ft.h:276,345`), so every transform
serialises twice.

To size it, the critical sections were instrumented to accumulate, per thread,
the time spent *waiting* to enter and the time spent *holding* the lock
(`FFTW_LOCK_STATS`, a diagnostic build only). Single movie, 5x5 patches:

| threads | plan create+destroy calls | total wait (thread-seconds) | total held (thread-seconds) | max single wait |
| --: | --: | --: | --: | --: |
| 1  | 3840 | 0.0003 | 0.245 | 0.000002 s |
| 4  | 3840 | 0.232  | 0.270 | 0.018 s |
| 16 | 3840 | 2.065  | 0.339 | 0.024 s |

Two corrections follow:

* **The call count is 3,840, not "over 7,300."** The issue's figure assumes
  `max_iter = 5` iterations of patch alignment. The movie converges in **2**.
  The measured 1,920 plan objects decompose exactly as
  24 (global FFT) + 24 (global iFFT) + 24 (dw iFFT) + 600 (prepare patch)
  + 48 (global align CCF, 2 iters) + 1200 (25 patches x 2 iters x 24 frames) = 1920,
  each costing one lock on construction and one on destruction.
* **The cost is not material.** Wait time is summed across threads, so 2.065
  thread-seconds at j=16 is ~0.13 s of wall on a run of ~5-7 s. The
  strictly-serial part (held time) is 0.34 s. Removing the lock entirely cannot
  recover more than a fraction of a second.

Worth noting for a future change: `FloatPlan` creates **both** a forward and a
backward plan, and every caller executes only one of them, so one plan per
construction is built and destroyed without ever being used. The share of the
0.245 s that represents was not measured separately (r2c and c2r planning need
not cost the same), but the whole figure is a fraction of a second, so it was
not pursued.

### Claim 2 and Claim 3 — dose weighting: cache thrashing and transcendental stalls

**Refuted as stated — the stage is dominated by FFTs, not by the quoted loop.**

Issue #26 attributes the whole `dose weighting` stage (19.27 s, "29% of total")
to the strided triple loop in `MotioncorrRunner::doseWeighting` and to
`std::exp`/`std::pow`. But `dose weighting` is an **outer** timer tag that
encloses two inner tags, and the inner split is:

| tag (j=1, cpu64, 5x5) | seconds | share of the `dose weighting` stage |
| :-- | --: | --: |
| `dose weighting` (outer) | 11.354 | 100% |
| ├ `dw - calc weight` — the loop the issue quotes | 2.943 | 26% |
| └ `dw - iFFT` — 24 inverse FFTs | 8.411 | **74%** |

So the arithmetic the issue analyses is **6.9% of total wall time**, not 29%.
The issue's own estimate that `std::exp` alone costs "2.5-4.0 s" is as large as
the entire measured loop including the `pow`, the `sqrt`, the `isnan` checks,
the complex multiply and the normalisation divide.

The quoted per-call counts are also slightly off because they use the unpadded
movie size: with the actual padded `Fframes` (1945 x 3888) it is 7.56 M `pow`
calls and 181.5 M `exp` calls, not 7.12 M and 171 M.

**Why the issue could not have seen this.** The harness that produced its stage
table, `tools/benchmark_cpu_profile.py`, parses timer lines with

```python
re.compile(r"^([A-Za-z0-9_ -()]+?)\s*:\s*([0-9.]+)\s*sec\s*\(([0-9.]+)\s*microsec/operation\)")
```

Inside that character class `' -('` is a **range** from `0x20` to `0x28`
(`space ! " # $ % & ' (`), so a literal `-` is not a member. Every timer tag
containing a hyphen is therefore silently unmatched: `dw - iFFT`,
`dw - calc weight`, `prep patch - FFT (in thread)`, `align - shift in Fourier
space` and the rest. The stage table can only ever show `dose weighting` as a
monolithic block, and the 74% of it that is inverse FFT is invisible by
construction. The tags are absent from `benchmark_results_full.json` entirely,
not merely from the rendered summary.

That regex was subsequently fixed (`bdfc374`, "fix(profiling): address PR review
comments on stats, regex, and gate reporting", 2026-09-23 17:15) on branch
`feat/issue-9-cpu-profiling-baseline` — but the benchmark artifacts behind Issue
#26 were generated at 15:19-15:46 the same day, **before** the fix, and that
branch has never been merged to `main`. The corrected data was never regenerated.

### Claim 4 — Amdahl's law and sequential overhead

**The serial budget is overstated by roughly an order of magnitude.**

Four of the five items the issue lists as "strictly single-threaded" are in fact
parallelised over frames, and measurably scale:

| issue's claim | actual pragma | j=1 | j=8 | scales? |
| :-- | :-- | --: | --: | :-- |
| TIFF read + decompression "≈1.94 s" | `motioncorr_runner.cpp:1265`, `num_threads(n_io_threads)` | 1.411 | 0.258 | yes, 5.5x |
| gain load / apply / header "≈0.70 s" | `:1279` `num_threads(n_threads)` | 0.093 | 0.034 | yes, 2.7x |
| defect + hot-pixel mask "≈0.20 s" | `:1293,1305,1310` | 0.060 | 0.043 | partly |
| SVD motion fit "≈0.15 s" | serial | 0.001 | 0.001 | genuinely serial, negligible |
| STAR + MRC write "≈0.65 s" | serial | — | — | genuinely serial |

The measured non-scaling residue (`read gain` 0.127 s -> 0.128 s, `fix defects`
0.030 s -> 0.029 s, `fit polynomial` 0.001 s) is on the order of **0.2 s**, not
the 3.6 s the issue's Amdahl parameterisation assumes. The resulting "asymptotic
ceiling ≤ 18.5x" is therefore not supported by the code it cites.

### Claim 5 — parallelism granularity and barriers

**Directionally right, with the wrong arithmetic, and one effect the issue missed.**

The patch loop is indeed sequential in `ipatch` with fine-grained parallel
regions inside, but the barrier count is 25 x **2** (measured convergence), not
25 x 5.

The granularity effect the issue does *not* mention is the more important one:
the frame loops run over **24** frames with the default static schedule. At
j=16 that is `ceil(24/16) = 2` rounds for 24 items in 32 slots — a hard **75%**
ceiling on every per-frame stage, independent of any lock, cache or NUMA effect.
This is visible as the j=16 knee in the sweep in section 3.

### Claim 6 — NUMA topology and cross-socket latency

**The stated hardware is wrong; the remedy the issue files under it is the single
largest measured effect in this whole investigation.**

The issue says the reference server has "64 physical cores divided into 8 NUMA
nodes (4 per socket)". `lscpu` on that host reports **2** NUMA nodes (0-61,
62-123) and a flat KVM topology of 124 sockets x 1 core. cpu64 likewise reports
2 nodes. There are no 8 NUMA nodes on either machine, so the specific
Infinity-Fabric latency argument is not applicable as written.

But the *experiment* the issue proposes under this heading (Phase 4:
`OMP_PROC_BIND` / `OMP_PLACES`) turns out to dominate everything else — see
section 3.2.

---

## 3. Measured strong scaling on cpu64

Single movie, `--patch_x 5 --patch_y 5 --dose_weighting`, 3 repetitions per
point, thread counts interleaved (rep 1 ascending, rep 2 descending, rep 3
ascending) so drift is spread across the sweep rather than landing on one `j`.
"foreign cores" is third-party CPU sampled once per second during each run,
excluding this session's own process tree.

### 3.1 Default (unbound) — reproduces Issue #26's phenomenon on different hardware

| j | wall s (median) | all reps | speedup | par. eff | user s | peak RSS GiB | foreign cores |
| --: | --: | :-- | --: | --: | --: | --: | :-- |
| 1  | 38.59 | 38.35, 38.59, 38.59 | 1.00x | 100.0% | 34.8 | 2.73 | 2.0 |
| 2  | 20.59 | 20.34, 20.59, 21.11 | 1.87x | 93.7%  | 35.2 | 2.77 | 2.1 |
| 4  | 16.89 | 11.83, 16.89, 16.96 | 2.29x | **57.1%** | 48.7 | 2.94 | 2.0 |
| 8  | 9.46  | 7.67, 9.46, 9.54    | 4.08x | 51.0%  | 50.1 | 3.18 | 2.1 |
| 16 | 7.01  | 6.94, 7.01, 7.01    | 5.50x | 34.4%  | 63.9 | 3.64 | 2.0 |

At j=4 this gives **2.29x / 57.1%**, against Issue #26's **2.23x / 55.8%** on the
4-gpu-vm. The phenomenon reproduces closely on completely different silicon, so
it is not an artifact of that host.

Note the **spread** at j=4 and j=8: 11.83 against ~16.9, and 7.67 against ~9.5,
while foreign load is flat at 2.0 cores. This is not measurement noise. Ten
repetitions at j=4 (section 3.6) show a dominant slow mode with occasional fast
runs, CV 9.6%, against CV 1.7% when threads are bound. Unbound scaling on this
host is a placement lottery, and a 3-repetition mean can land anywhere in it.

### 3.2 With `OMP_PROC_BIND=spread OMP_PLACES=cores` — the dominant effect

Identical binary, identical inputs, one environment variable pair:

| j | wall s (median) | all reps | speedup | par. eff | user s |
| --: | --: | :-- | --: | --: | --: |
| 1  | 38.52 | 38.41, 38.52, 39.06 | 1.00x | 100.0% | 34.7 |
| 2  | 22.40 | 22.35, 22.40, 23.05 | 1.72x | 86.0%  | 37.1 |
| 4  | 11.88 | 11.75, 11.88, 11.90 | 3.24x | **81.1%** | 37.6 |
| 8  | 6.74  | 6.70, 6.74, 6.85    | 5.72x | 71.4%  | 40.0 |
| 16 | 5.18  | 5.16, 5.18, 5.31    | 7.44x | 46.5%  | 48.3 |

| j | unbound | spread | wall change |
| --: | --: | --: | --: |
| 1  | 38.59 | 38.52 | -0.2% |
| 2  | 20.59 | 22.40 | **+8.8% (worse)** |
| 4  | 16.89 | 11.88 | **-29.7%** |
| 8  | 9.46  | 6.74  | **-28.8%** |
| 16 | 7.01  | 5.18  | **-26.1%** |

Three things to take from this:

* **Parallel efficiency at j=4 goes from 57.1% to 81.1% with no code change.**
  User time falls with wall time (48.7 s -> 37.6 s at j=4), so this is genuine
  efficiency recovered, not wall-clock shuffling.
* **The variance collapses.** The bimodal spread at j=4 (11.83-16.96) becomes
  11.75-11.90. Unbound scaling is a placement lottery; binding removes the
  lottery as well as the loss.
* **`spread` is not universally right.** At j=2 it is 8.8% *worse* than unbound,
  because on a 2-socket box `spread` puts 2 threads maximally apart — i.e. on
  different NUMA nodes. This is the one place where Issue #26's NUMA reasoning
  bites, and it bites in the opposite direction from the one it predicted.

### 3.3 Which affinity setting — and a trap

Four settings, same binary, 5x5, median wall (2 reps for close/places-only,
3 for the others):

| j | unbound | `spread`+`cores` | `close`+`cores` | `OMP_PLACES=cores` alone |
| --: | --: | --: | --: | --: |
| 2  | **20.59 s** | 22.40 s | 34.60 s | 35.09 s |
| 4  | 16.89 s | **11.88 s** | 18.25 s | 18.32 s |
| 8  | 9.46 s  | **6.74 s**  | 10.11 s | 9.98 s |
| 16 | 7.01 s  | **5.18 s**  | 7.38 s  | 7.35 s |

Two practical points, and one piece of mechanism:

* **"Just enable affinity" makes things worse.** `OMP_PLACES=cores` on its own
  enables binding under libgomp's default policy, which packs; it tracks `close`
  almost exactly and is worse than doing nothing at every thread count. Only
  `spread` helps. A recommendation that says "set OMP_PLACES" without saying
  "and OMP_PROC_BIND=spread" is a pessimisation.
* **At j=2, unbound wins.** `spread` on a 2-socket box puts two threads on
  different sockets (+8.8%); `close` puts them somewhere much worse (+68%);
  the default scheduler happens to pick two distinct cores on one socket.

The `close` result is the clearest evidence for the mechanism. At j=2 it is
68% slower than unbound while its *user* time nearly doubles (61.9 s against
35.2 s) — the signature of two threads sharing one physical core's execution
resources while OpenMP spin-waiting burns the difference. The guest reports
`Thread(s) per core: 1` and lists every CPU as its own thread sibling, so this
SMT structure is invisible from inside the VM and can only be inferred from
timing. See section 6 item 1 for why this remains an inference.

### 3.4 The machine's own ceiling — is MotionCorr even the limiting factor?

To separate "MotionCorr scales badly" from "this machine scales badly", the same
thread counts were run on standalone kernels with no locks, no barriers beyond
one join, and (for the first) no memory traffic at all. Work scales with `j`, so
perfect scaling is flat time / 100% per-thread throughput.

| j | `exp()` throughput, unbound | `exp()` throughput, spread+cores | FMA throughput, unbound |
| --: | --: | --: | --: |
| 1  | 100.0% | 100.0% | 100.0% |
| 2  | **62.5%** | 100.5% | 98.5% |
| 4  | 62.0% | 100.3% | 94.6% |
| 8  | 62.0% | 97.6%  | 70.2% |
| 16 | 61.9% | 96.5%  | 66.6% |
| 32 | 60.3% | 61.9%  | 66.1% |
| 64 | 51.9% | 38.1%  | 54.2% |

A kernel that does nothing but call `exp()` in registers loses 38% of its
per-thread throughput the moment a second thread starts, and recovers all of it
under `spread`+`cores`. **That loss is a property of this machine and its
default thread placement, not of MotionCorr.** Any analysis that attributes it
to FFTW locks, cache thrashing or barrier counts is attributing a machine
property to source code.

Memory bandwidth was also characterised (STREAM-style triad, 64 MiB/thread):
25 GiB/s at j=1, 92.9 at j=8, 100.7 at j=16, 100.9 at j=32 — saturating around
j=8-16. MotionCorr's own traffic is far below this: the dose-weighting stage
moves ~2.9 GB in 2.67 s at j=1, about 1.1 GiB/s. Claim 2's "saturating the L3
cache and memory bus" at j=4 is therefore not quantitatively supported.

### 3.5 Where the time actually goes

Stage timers, `--patch_x 5 --patch_y 5`, unbound, median of 3:

| stage | j=1 (s) | j=16 (s) | speedup |
| :-- | --: | --: | --: |
| dose weighting *(outer, contains the two below)* | 10.674 | 1.557 | 6.86x |
| ├ `dw - iFFT` | 8.003 | 1.228 | 6.52x |
| └ `dw - calc weight` *(the loop Issue #26 analyses)* | 2.671 | 0.328 | 8.14x |
| global iFFT | 8.557 | 1.323 | 6.47x |
| global FFT | 7.763 | 1.168 | 6.65x |
| prepare patch | 4.269 | 0.760 | 5.62x |
| real space interpolation | 3.471 | 0.417 | 8.32x |
| read movie | 1.383 | 0.178 | 7.77x |
| align - shift in Fourier space | 0.846 | 0.246 | 3.44x |
| global alignment | 0.666 | 0.206 | 3.23x |
| patch alignment | 0.659 | 0.297 | 2.22x |
| read gain | 0.104 | 0.110 | **0.95x (serial)** |
| initial sum | 0.092 | 0.018 | 5.11x |
| apply gain | 0.088 | 0.029 | 3.03x |
| detect hot pixels | 0.060 | 0.043 | 1.40x |
| fix defects | 0.029 | 0.031 | **0.94x (serial)** |

**Fourier transforms are ~74% of the j=1 runtime** (`global FFT` + `global iFFT`
+ `dw - iFFT` + the FFT inside `prepare patch` + the CCF transforms ~ 28.7 s of
38.59 s). That, not lock contention and not dose-weighting arithmetic, is the
decisive cost centre.

The measured strictly-serial residue is `read gain` + `fix defects` +
`fit polynomial` ~ **0.14 s**, against the 3.6 s Issue #26's Amdahl argument
assumes.

**A caveat on the `(in thread)` tags.** `Timer::toc` in `src/time.cpp` does an
unsynchronised `times[timer] +=` and writes a shared `end_time` member, and the
`(in thread)` tags are ticked from inside parallel regions. The corruption is
directly visible in the data: `prep patch - FFT (in thread)` reports 4.083
thread-seconds at j=1 but only 2.179 at j=16 — less total thread-time than the
serial case, which is impossible without lost updates. Those rows must not be
used quantitatively. A per-thread Timer exists on branch
`feat/issue-9-cpu-profiling-baseline` but has never been merged to `main`.

### 3.6 The placement lottery, n=10 at j=4

Ten repetitions each, same binary, 5x5, run back to back; peak third-party load
5.2 and 5.5 cores respectively, so the two arms saw comparable conditions:

| | n | min | median | max | sd | CV |
| :-- | --: | --: | --: | --: | --: | --: |
| unbound | 10 | 13.22 s | 18.58 s | 19.05 s | 1.73 | **9.6%** |
| `spread`+`cores` | 10 | 12.35 s | **12.57 s** | 12.97 s | 0.22 | **1.7%** |

Unbound: `13.22, 17.55, 18.25, 18.44, 18.58, 18.58, 18.73, 18.76, 18.88, 19.05`
Bound: `12.35, 12.43, 12.44, 12.50, 12.53, 12.60, 12.79, 12.80, 12.88, 12.97`

Binding is worth 32% at the median here and cuts the coefficient of variation by
5.6x. (Both arms are slower in absolute terms than sections 3.1-3.2 because they
ran later in the session under a slightly higher residual load; the within-pair
comparison is unaffected.)

### 3.7 Single NUMA node (`numactl --cpunodebind=0 --membind=0`)

Issue #26's Phase 4 proposed this as the NUMA remedy. Measured, 5x5, 2 reps:

| j | unbound | numactl node 0 | spread+cores |
| --: | --: | --: | --: |
| 8  | 9.46 s | 9.39 s (-0.7%) | 6.74 s (-28.8%) |
| 16 | 7.01 s | 6.75 s (-3.7%) | 5.18 s (-26.1%) |

Confining the process to one NUMA node is worth a few percent. Binding threads to
distinct cores is worth ~27%. Both were filed under the same claim in the issue;
they are not the same size, and only one of them matters.

### 3.8 Whole-dataset throughput: process count beats thread count

All 24 tutorial movies, **16-core budget held constant**, movies dealt round-robin
across processes. `--patch_x 1 --patch_y 1 --dose_weighting`.

| layout | baseline wall | baseline movies/min | candidate wall | candidate movies/min |
| :-- | --: | --: | --: | --: |
| 1 proc x 16 thr | 121.8 s | 11.83 | 96.7 s | 14.89 |
| 2 proc x 8 thr  | 91.5 s  | 15.74 | — | — |
| **4 proc x 4 thr** | **84.2 s** | **17.10** | **62.0 s** | **23.21** |
| 8 proc x 2 thr  | 86.0 s  | 16.75 | — | — |

With 5x5 patches, baseline: 1x16 = 171.3 s (8.41 movies/min), 4x4 = 108.3 s
(13.29 movies/min).

**At a fixed core budget, 4 processes x 4 threads delivers 1.45x the throughput
of 1 process x 16 threads** (1.58x for 5x5). Intra-movie parallelism is the
inefficient axis; movie-level parallelism is nearly free. For dataset processing
this is a larger and cheaper win than anything in Issue #26's roadmap, and it
requires no code change at all.

Adding `OMP_PROC_BIND=spread OMP_PLACES=cores` to the 1x16 dataset layout gave
115.4 s vs 121.8 s (+5.5% throughput) — much less than the 26% it gives on a
single movie, because the per-movie serial tail (MRC write, EPS/PDF generation)
is a larger share of a dataset run and does not benefit.

### 3.9 Thread binding is actively harmful for multi-process layouts

The same affinity setting applied to the 4 x 4 layout:

| layout | unbound | `OMP_PROC_BIND=spread OMP_PLACES=cores` |
| :-- | --: | --: |
| 1 proc x 16 thr | 121.8 s | 115.4 s (-5.3%) |
| 4 proc x 4 thr  | 84.2 s  | **255.0 s (+203%)** |

Each process binds *independently* against the same place list, so all four
place their 4 threads on the same 4 physical cores and then fight over them. A
3x slowdown, from the setting that is worth +26% for a single process.

This is why the change in this branch does **not** set affinity from inside the
binary. MotionCorr cannot know whether it is the only process on the machine,
and the failure mode when it guesses wrong is far worse than the win when it
guesses right. (It could not do so reliably in any case: libgomp reads
`OMP_PROC_BIND` in a shared-library constructor that runs before the
executable's own constructors, and a `proc_bind(spread)` clause is ignored
unless binding is already enabled — both verified on this host.)

The correct recommendation is therefore conditional, and belongs in operator
documentation rather than in the binary:

* **one process, many threads** -> `OMP_PROC_BIND=spread OMP_PLACES=cores`
  (worth ~26% at j >= 4; skip it at j=2, where it costs ~9%);
* **several processes** -> give each a *disjoint* CPU set with `taskset` or
  `numactl`, and leave `OMP_PROC_BIND` unset. Never let independent processes
  bind against the same place list.

---

## 4. The change in this branch: skip a provably dead inverse FFT

### What it does

`MotioncorrRunner::executeOwnMotionCorrection` inverse-transforms all frames
into real space immediately after global alignment
(`src/motioncorr_runner.cpp`, the `TIMING_GLOBAL_IFFT` block). Those real-space
frames are read again in exactly two places:

* patch clipping, guarded by `do_local = (patch_x > 2) && (patch_y > 2)`;
* the "summing frames before dose weighting" block, guarded by
  `if (!do_dose_weighting || save_noDW)`.

When **neither** guard is satisfied — that is, dose weighting is on, `--save_noDW`
is off, and there are fewer than three patches per axis — every value written by
that transform is overwritten by the post-dose-weighting inverse FFT before
anything reads it. The transform is dead work.

`--patch_x` and `--patch_y` both **default to 1**, so a plain
`motioncorr --use_own --dose_weighting ...` hits this path.

The change computes `do_local` a few lines earlier (it was already computed
further down, from the same two variables) and skips only the transform:

```cpp
const bool do_local = (patch_x > 2) && (patch_y > 2);
const bool need_real_space_before_dw = do_local || !do_dose_weighting || save_noDW;

#pragma omp parallel for num_threads(n_threads)
for (int iframe = 0; iframe < n_frames; iframe++) {
    Iframes[iframe]().reshape(ny, nx);
    if (need_real_space_before_dw)
        NewFFT::inverseFourierTransform(Fframes[iframe], Iframes[iframe]());
}
```

The `reshape` is deliberately kept so allocation behaviour and peak RSS are
unchanged; only the transform is elided. This is an elision of unread work, not
a numerical approximation — there is no tolerance to argue about.

The inefficiency is inherited from upstream RELION 5.1, not introduced by this
repository's extraction.

### Why it is not the answer to the general scaling question

It removes work; it does not improve scaling. It helps the global-only
configuration and is a no-op for `--patch_x 5 --patch_y 5`. It is included
because it is a real, safe, sizeable saving that the investigation surfaced, not
because it addresses Issue #26's headline efficiency number.

### Test coverage, and proof that the guards can fail

`tests/test_synthetic_regression.py` runs with `--patch_x 3`, so it only ever
exercises the untouched branch. A new test,
`tests/test_global_only_dose_weighting.py` (CTest name
`GlobalOnlyDoseWeighting`), covers the changed one. It needs no new reference
fixture; its two checks guard the two ways the skip condition can go wrong:

1. **Too narrow / a new reader appears.** With
   `--patch_x 1 --patch_y 1 --dose_weighting`, the dose-weighted micrograph must
   be bit-identical with and without `--save_noDW`. Those two invocations take
   opposite branches — confirmed directly with the stage timer: `global iFFT`
   reads **0 s** without `--save_noDW` and **8.942 s** with it, on the same
   binary.
2. **Too broad.** `--patch_x 3` must not produce the same micrograph as
   `--patch_x 1`. If the skip were widened to cover `do_local`, patch clipping
   would read frames that were never transformed, every patch would report zero
   shift, and the patched result would silently collapse to the global-only one.

**Both claims were checked against a deliberately broken build** (skip condition
hardcoded to `false`, so the transform is always elided):

| guard | baseline | candidate | deliberately-broken build |
| :-- | :-- | :-- | :-- |
| `SyntheticRegression` (`--patch_x 3`) | PASS | PASS | **FAIL** (max pixel diff 10.32) |
| `GlobalOnlyDoseWeighting` check 1 | PASS | PASS | pass — *cannot see this failure mode* |
| `GlobalOnlyDoseWeighting` check 2 | PASS | PASS | **FAIL** (`--patch_x 3` == `--patch_x 1`) |

Check 1 passing on the broken build is expected, not a defect: both of its arms
skip there, so they still agree. It is recorded because a guard whose power has
not been demonstrated should not be described as if it had been. Check 2 was
added specifically because check 1 alone could not see an over-broad condition.

An incidental finding from the broken build: with the transform always elided,
`--patch_x 5` on the tutorial movie produces *exactly* the global-only digest
(`ed33b629…` instead of `bf738254…`) while the log still reports plausible
per-patch RMSD values. A silently degraded patch alignment is therefore not
visible in the log — only in the output.

---

## 5. Measured effect of the change

Paired, arm order alternating within each pair, on an otherwise quiet box
(third-party load flat at 2.0 cores throughout, sampled once per second).

| arm | config | j | base median | cand median | mean delta | sd | change | pairs cand faster |
| :-- | :-- | --: | --: | --: | --: | --: | --: | :-- |
| E | global-only | 1 | 30.205 s | 22.175 s | **-7.952 s** | 0.251 | **-26.4%** | **6/6** |
| F | global-only | 8 | 7.475 s  | 5.820 s  | **-1.673 s** | 0.253 | **-22.5%** | **6/6** |
| G | 5x5 patches | 8 | 9.210 s  | 9.610 s  | -0.085 s | 1.252 | -0.9% | 2/4 |

Arm G is the control: the change must be a no-op with 5x5 patches. The measured
delta is indistinguishable from zero, though with only 4 pairs in the bimodal
unbound regime the interval is wide (sd 1.25 s) and the timing alone would not
exclude a small effect. The *decisive* evidence that 5x5 is untouched is not
statistical: `do_local` is true there, so the guarded call executes exactly as
before, and the outputs are bit-identical.

Positional bias (the advantage to whichever arm runs second, recovered from the
same data by splitting pairs on ordering) was -0.148 s at j=1 and -0.173 s at
j=8 — small against a 7.95 s and 1.67 s effect respectively.

Stage evidence, `-DTIMING` builds, global-only, 3 alternating repetitions —
this is contention-immune in a way process wall is not, because it shows the
work is gone rather than merely faster:

| | baseline | candidate |
| :-- | :-- | :-- |
| `global iFFT` | 8.388 / 9.114 / 9.361 s | **0.000 / 0.000 / 0.000 s** |
| process wall | 29.79 / 32.29 / 33.06 s | 22.26 / 21.93 / 21.81 s |
| `global FFT` (unchanged control) | 7.752 / 8.436 / 8.464 s | 7.817 / 7.724 / 7.756 s |
| `dw - iFFT` (unchanged control) | 7.802 / 8.485 / 8.803 s | 8.544 / 8.286 / 8.287 s |

### Numerical gates

No gate was relaxed. Comparison splits the MRC into pixel payload (bytes 1024+)
and core header (bytes 0-223), because the label area at offset 224 carries a
`strftime` timestamp that differs between any two runs.

| gate | scope | result |
| :-- | :-- | :-- |
| pixels + core header + per-movie STAR | global-only j=1 (the changed path) | **bit-exact** |
| pixels + core header + per-movie STAR | global-only + `--save_noDW` j=4 | **bit-exact** |
| pixels + core header + per-movie STAR | 5x5 patches j=4 | **bit-exact** |
| distinct pixel digests across j=1,2,4,8,16 | 5x5, unbound and spread arms | **1** |
| distinct pixel digests across all paired runs | arms E, F, G | **1 per arm** |
| **24-movie dataset, baseline vs candidate** | 6 layouts x 24 movies = 144 outputs, j in {2,4,8,16}, procs in {1,2,4,8} | **0 mismatches** |
| `tests/test_synthetic_regression.py` (`--j 1`, `--j 4`) | repo CI gate | **PASS, bit-for-bit** |

The 24 baseline pixel digests combine to `a3fff21571527a921ca794fc98dc9dad…`;
the candidate reproduces every one of them.

As a side observation relevant to Issue #20/#50: across every run recorded here
— both binaries, j from 1 to 16, 1 to 8 concurrent processes — the output pixel
digest never varied. On this movie set and configuration the CPU path was
thread-count independent.

## 6. What remains open

These are not covered by the measurements above and should not be quoted as
settled.

1. **Why unbound placement costs what it does.** The effect is measured and
   repeatable, but the *mechanism* is inferred. From inside the guest,
   `lscpu` reports 1 thread per core and `/sys/.../thread_siblings_list`
   lists each CPU alone, so the guest cannot see whether its 64 vCPUs are
   backed by 64 physical cores or by 32 cores with SMT. The observed pattern
   (full throughput up to j=16 when spread, ~62% when packed, degradation for
   both beyond j=16) is consistent with SMT-sibling co-scheduling, but
   confirming it requires host-side topology from whoever administers the
   hypervisor. Frequency behaviour is equally invisible — there is no
   `cpufreq` interface and `cpu MHz` is a fixed nominal value — so an
   all-core clock drop cannot be excluded as a contributor.

2. **Whether the same placement effect explains Issue #26's original numbers.**
   Those were taken on the 4-gpu-vm, a different machine (EPYC 7452, 124 vCPU).
   This investigation deliberately kept CPU-only workloads off that shared GPU
   host, so the affinity arm was **not** re-run there. Until it is, the claim
   "#26's 56% efficiency is mostly placement" is an extrapolation from cpu64,
   not a measurement of the host #26 used.

3. **Hardware counters.** No IPC, cache-miss or memory-bandwidth data was
   collected for MotionCorr itself, for the reasons in section 1. The
   memory-bandwidth ceiling was characterised only with a separate STREAM-like
   control, which bounds the plausible contribution but does not measure
   MotionCorr's actual traffic.

4. **The real remaining bottleneck is FFT throughput, and it is untouched.**
   At j=1, FFT work is ~75% of the run. Two untested levers: reusing one
   `FloatPlan` across all frames of a given size instead of constructing and
   destroying 1,920 of them, and using FFTW's own threaded transforms
   (`fftwf_plan_with_nthreads`) so parallelism is not capped by the 24-frame
   loop. The first is very likely bit-exact; the second is not obviously so and
   would need a parity gate before it could be considered.

5. **The 24-frame static-schedule ceiling at j >= 16.** Identified
   analytically and consistent with the measured knee, but no fix was
   implemented or tested.

## 7. Concrete next experiment

Run the affinity arm on the 4-gpu-vm under its 8-CPU allocation, comparing
`taskset -c 96-103` alone against `taskset -c 96-103` with
`OMP_PROC_BIND=spread OMP_PLACES=cores`, paired with arm order alternating, at
j=1/2/4/8 on the same movie. That single experiment decides whether Issue #26's
headline 56% figure is a property of MotionCorr or of how threads were placed on
that host, and it is the difference between "optimise the code" and "fix the
launch environment" as the project's next unit of work. It must be queued behind
`flock /tmp/motioncorr-bench.lock` on that box, and it competes with GPU work for
the same 8 CPUs, so it should be scheduled rather than run opportunistically.
