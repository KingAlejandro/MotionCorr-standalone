# What the multi-GPU setup cost is, and why it scales negatively

Measured on `4-gpu-vm`, source `ff30678`, plus a standalone probe
(`cuda_init_probe.cu`) that uses no MotionCorr code.

## Answer

**CUDA context creation, and essentially nothing else.** It costs 255 ms in one
process, and it serialises across concurrent processes *regardless of which GPU
they target*, reaching 863 ms at four.

Probe, one process, median of 5:

| stage | ms | share |
|---|---:|---:|
| **context creation** | **254.7** | **97 %** |
| first cuFFT plan (3710×3838 R2C) | 4.7 | 1.8 % |
| second identical plan | 1.8 | 0.7 % |
| first device malloc (57 MB) | 0.2 | 0.1 % |
| first kernel launch | 0.2 | 0.1 % |

## Why it scales negatively

| concurrent processes | context creation | vs 1 process |
|---:|---:|---:|
| 1 | 254.7 ms | ×1.00 |
| 2 | 432.4 ms | ×1.70 |
| 3 | 636.0 ms | ×2.50 |
| 4 | 862.6 ms | ×3.39 |

Four processes on four **different** GPUs still cost ×3.39, so roughly 85 % of
context creation is serialised. The control that settles it: four processes on
**one** GPU cost ×3.02 — statistically the same. Sharing a GPU makes no
difference, so this is not per-device contention but a resource global to the
driver or host.

Everything else in the probe is flat or near-flat under concurrency (kernel
launch ×1.00, plans ×1.21–1.25 on distinct GPUs).

## It is not persistence mode

Persistence mode was found disabled, which normally makes context creation
expensive because the driver tears the GPU down between clients. Enabling it
changed nothing:

| procs | pm off | pm on | speedup |
|---:|---:|---:|---:|
| 1 | 254.7 ms | 251.1 ms | ×1.01 |
| 4 | 862.6 ms | 861.6 ms | ×1.00 |

Scaling was ×3.39 off and ×3.43 on. The setting was reverted to its original
disabled state. Retained as a negative result so it is not retried.

## How it appears in a real run

MotionCorr makes its first CUDA call inside the first movie, so context
creation is billed to that movie rather than to startup:

| GPUs | true startup | 1st movie | later movies | warm-up penalty | probe context | ratio |
|-----:|-------------:|----------:|-------------:|----------------:|--------------:|------:|
| 1 | 0.127 s | 0.865 s | 0.466 s | 0.399 s | 0.255 s | 1.56 |
| 2 | 0.215 s | 0.927 s | 0.471 s | 0.457 s | 0.432 s | 1.06 |
| 3 | 0.275 s | 1.100 s | 0.485 s | 0.615 s | 0.636 s | 0.97 |
| 4 | 0.340 s | 1.220 s | 0.516 s | 0.704 s | 0.863 s | 0.82 |

The warm-up penalty tracks the independently-measured context cost. At 1 GPU
the ratio is 1.56 because the penalty also carries the first cuFFT plans and
allocations; those stop mattering as context creation grows.

## Corrections to the earlier timing record

Both were artifacts of defining `setup` as launch → first product, which
contains the entire first movie. `MULTIGPU_TIMING.md` states the superseded
figures.

- Setup is **not** 1.61 s at 4 GPUs and not the largest non-scaling term. True
  startup is 0.127 s → 0.340 s.
- Per-movie work does **not** degrade 27 %. Steady state is 0.466 → 0.516 s,
  **+10.7 %**. The 27 % averaged the expensive first movie in, and the first
  movie is 1/6 of the work at 4 GPUs against 1/24 at 1 GPU.
- "Produce scales at ×4.12" was super-linear only because the first movie sat
  outside it.

Corrected 4-GPU overhead against a perfectly-scaling 2.80 s:

| term | cost | share of overhead |
|---|---:|---:|
| context-creation warm-up | 0.70 s | 31 % |
| aggregate tail | 0.73 s | 32 % |
| true startup | 0.34 s | 15 % |
| steady-state per-movie degradation | 0.30 s | 13 % |

Three comparable terms, not one dominant one.

## What this means for the 4-GPU verdict

Warm-up, tail and startup total **1.78 s of per-run cost that no dataset size
reduces**. On 24 movies that is most of the gap. Extrapolating the measured
steady-state rate:

| movies | ideal 4-GPU | projected | efficiency |
|-------:|------------:|----------:|-----------:|
| 24 | 2.8 s | 4.9 s | 57 % |
| 100 | 11.7 s | 14.7 s | 79 % |
| 500 | 58.2 s | 66.3 s | 88 % |
| 1000 | 116.5 s | 130.8 s | 89 % |

The 24-movie row reproduces the measured 5.06 s and 55 %, so the model is
anchored at the measured end. **This is a projection, not a measurement** — it
assumes the steady-state rate holds and that nothing new contends at scale,
neither of which has been tested. The tutorial set is simply too small to
amortise a fixed 1.78 s.

The poor 4-GPU efficiency is a small-dataset artifact, not a property of
process-per-GPU sharding.

## The fixed cost is not fixed

Fitting `wall = C + m·k` separately at each worker count, on the retained sweep
points, gives intercepts that grow linearly with worker count:

| workers | intercept | tail intercept | tail per movie |
|--------:|----------:|---------------:|---------------:|
| 1 | 1.099 s | 0.503 s | 17.8 ms |
| 2 | 1.256 s | 0.549 s | 13.2 ms |
| 4 | 1.800 s | 0.761 s | 4.5 ms |

    fixed(n) = 0.826 + 0.239 · n        residuals <= 0.05 s

**Each worker added costs 0.24 s of per-run time**, and a `C + W/n` model has no
term that can express it, so its intercept silently absorbs the growth. That is
why the three-point fit in `MULTIGPU_TIMING.md` reported C = 2.48 s when the
n=4 fixed cost is actually 1.80 s.

The probe ties the mechanism to that slope independently. Fitting its context
cost the same way gives `ctx(n) = 0.040 + 0.203·n`, so **CUDA context creation
accounts for 85 % of the per-worker growth** (0.203 of 0.239 s). The probe
shares no code with MotionCorr, so this is confirmation of the mechanism rather
than a restatement of the same measurement.

The tail also turns out not to be purely fixed: it carries 17.8 ms per movie at
one worker, and that component divides across workers (4.5 ms at four), which
the earlier per-run tail figure did not separate.

### Resulting model

    T(n, M) = 0.826 + 0.239·n + (M/n)·w(n)      w measured: 0.466 0.471 0.485 0.516

| n | predicted | measured | error |
|--:|----------:|---------:|------:|
| 1 | 12.25 s | 12.98 s | -0.73 |
| 2 | 6.96 s | 7.23 s | -0.27 |
| 3 | 5.42 s | 5.67 s | -0.25 |
| 4 | 4.88 s | 5.06 s | -0.18 |

It under-predicts by 0.2-0.7 s because it omits the launcher's own prologue and
the movie-1 excess beyond context creation. The structure is the point, not the
last 5 %.

Because the `0.239·n` term grows while `(M/n)·w` shrinks, there is an optimal
worker count rather than "more is better". At 24 movies it is around 7 — beyond
the 4 GPUs available, which is why more GPUs still helped here. **Anything past
n=4 is extrapolation**: `w(n)` is measured only to four workers and is itself
rising, so the true optimum is lower than `sqrt(M·w/0.239)` suggests.

## Correction: DIRECT does not measure what I claimed

`MULTIGPU_TIMING.md` calls `--only_do_unfinished` over a complete tree a third
independent route to the fixed cost. It is not the same quantity.

`isMovieComplete` (`src/motioncorr_runner.cpp:659`) opens the corrected MRC
header and parses the per-movie STAR **three times** — `general.read` at :669,
`shifts.read` at :675, and a full `Micrograph` construction at :694. So DIRECT
pays a 24-movie completion scan that a normal run does not, while skipping the
CUDA initialisation that a normal run does pay. Its flatness across worker
counts (0.97 s at 1, 0.95 s at 4) is consistent with that: no context creation,
so none of the 0.203 s/worker growth.

The two routes that do measure the fixed cost — the phase split and the sweep
intercept — still agree. DIRECT remains useful as a bound on the non-CUDA part,
which is what it actually measures.

## Reducing it

Nothing cheap. One context per process is inherent to process-per-GPU, and the
cost is driver-side: not persistence mode, not plan construction, not
allocation. Options are MPS (shares one context, changes the execution model),
fewer larger workers, or accepting it — which on any realistic dataset is the
right answer, since it is a fixed 1.78 s.

## Evidence

- `cuda_init_probe.cu` — the probe; `nvcc -O2 -arch=sm_80 -lcufft`
- `evidence/probe_persistence_off.txt`, `evidence/probe_persistence_on.txt` — 65 samples each
