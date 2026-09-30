# Where multi-GPU time actually goes

Instrumented timing campaign on `4-gpu-vm`, source `ff30678`. 64 runs.
Figures in `figures/` (`index.html` for the dashboard; SVGs are light/dark pairs).

## Result

The per-movie work scales better than linearly. **Everything that fails to scale is
setup and the aggregate tail**, and at 4 GPUs those are 48 % of the wall.

| GPUs | wall | speedup | eff. | setup | produce | tail | fixed (setup+tail) | produce speedup |
|-----:|-----:|--------:|-----:|------:|--------:|-----:|-------------------:|----------------:|
| 1 | 12.98 s | ×1.00 | 100 % | 0.99 | 10.95 | 0.94 | 1.93 s (15 %) | ×1.00 |
| 2 | 7.23 s | ×1.80 | 90 % | 1.17 | 5.27 | 0.79 | 1.96 s (27 %) | ×2.08 |
| 3 | 5.67 s | ×2.29 | 76 % | 1.39 | 3.48 | 0.79 | 2.18 s (38 %) | ×3.15 |
| 4 | 5.06 s | ×2.56 | 64 % | 1.61 | 2.66 | 0.82 | 2.43 s (48 %) | ×4.12 |

24 movies, median of 7 interleaved repeats, 32 whole cores of budget in every arm.
`setup` is launch to first product, `produce` is first to last product, `tail` is last
product to exit; the three partition each worker's wall exactly, and the table reports
the worst worker per run.

## It is not data transfer

Two independent reasons, both measured:

- Transfer is inside `produce`, which scales at ×4.12 on four GPUs. A term that
  scales cannot cause the non-linearity.
- PCIe is nearly idle. On the nvCOMP route only compressed bytes cross the bus:
  2.98 GiB for the whole dataset, **0.57 GiB/s aggregate at 4 GPUs, 0.6 % of a
  PCIe4 x16 link**. Even the float route would be 6 %. Per-GPU bandwidth *falls* as
  GPUs are added (0.23 → 0.14 GiB/s), so there is no transfer pressure to relieve.

## Setup contends, it does not serialise

Setup grows with worker count — 0.99 → 1.17 → 1.39 → 1.61 s — while the stagger
between workers reaching their first product stays near zero (0.000 → 0.035 → 0.029
→ 0.068 s).

Those two facts together rule out queueing. If concurrent per-process CUDA
initialisation serialised, worker *k* would start producing after *k* setup periods
and the spread would grow to roughly 3 × 0.4 s at four workers. It stays at 68 ms.
Instead every worker's setup gets uniformly slower, which is contention on a shared
host or driver resource during concurrent initialisation.

This corrects the hypothesis recorded in `ff30678`, which predicted a growing spread
if setup serialised. The instrumentation refuted it on its first run.

## Two routes to the fixed cost agree

A movie-count sweep (4/8/12/24 movies) fits `wall = C + m·k`:

| GPUs | fixed C | per movie |
|-----:|--------:|----------:|
| 1 | 1.10 s | 489 ms |
| 2 | 1.26 s | 350 ms |
| 4 | 1.80 s | 141 ms |

C from the sweep tracks setup+tail from the phase split (1.10 vs 1.93, 1.80 vs 2.43;
the sweep intercept is lower because shard sizes are integers, so adding one movie to
the dataset does not add 1/n of a movie to the critical worker).

A third route agrees on the non-CUDA part: `--only_do_unfinished` over an already
complete tree, which skips every movie and therefore never initialises CUDA, takes
0.97 s at 1 GPU and 0.95 s at 4 — flat. Subtracting it from the sweep intercept
leaves 0.25 s at 1 GPU and 1.13 s at 4 for CUDA setup, the same ×4.5 growth the phase
split shows.

## Ruled out by measurement

- **`--skip_logfile` on sharded workers.** Predicted 0.4–1.0 s at 4 GPUs from a
  retained PR90 timing. Measured saving: **0.02 s (0.4 %)**. The PDF tail is real
  (0.60 s of the 1-GPU fixed cost) but at 4 GPUs each worker's tail is smaller and
  overlaps the others, so it leaves the critical path. At 1 GPU it does save 0.52 s
  (4.0 %).
- **Host CPU.** Peak 5.04 busy cores of 32 allocated.
- **Memory.** Peak RSS ~0.55 GiB per worker.

## Where the remaining headroom is

1. **Concurrent CUDA/plan initialisation, 1.61 s at 4 GPUs and growing with worker
   count.** The largest single non-scaling term. Worth attributing further before
   attempting a fix: it is not yet separated into context creation, cuFFT planning
   and first-touch allocation.
2. **The aggregate tail, ~0.8 s and flat.** Already shown not to be worth removing by
   flag at 4 GPUs.
3. Nothing in the per-movie path, on this evidence.

## Venue

`4-gpu-vm`, 4× A100 80GB PCIe, EPYC 7452, 124 vCPUs no SMT, THP `madvise`, local
input, under `flock /tmp/motioncorr-bench.lock`. Zero foreign GPU compute apps
throughout. Not comparable in absolute terms to SCARF gn3002 (SXM4, PanFS, THP
`always`) — see `MULTIGPU_4GPUVM.md`.

## Reproducing

    python3 docs/post128/make_charts.py <status-dir> docs/post128/figures

Reads the `status.json` files the launcher already writes, so no number is retyped
between measurement and figure. Pure stdlib — the validation hosts have no numpy.
