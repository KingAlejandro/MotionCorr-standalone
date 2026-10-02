# Single-GPU pooling: measured result, 2 October 2026

Measurement for `perf/single-gpu-pools`. Everything here was executed on native GPU
hardware on the dates and source pins given below. Nothing is calculated from another
campaign and nothing is relabelled from an earlier one.

## Venue and provenance

| | |
|---|---|
| Host | `4GPUs` (`4-gpu-vm`), 124 CPUs, THP `madvise` |
| Device | A100 80GB PCIe, `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, pinned by UUID |
| Toolchain | CUDA 12.8, nvCOMP 5.3.0.16, cmake 3.28.3, python 3.12.3 |
| Build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DUSE_NVCOMP=ON`, one build per arm |
| Payload | `taskset -c 64-71`, `OMP_NUM_THREADS=6`, `--j 6 --max_io_threads 6` |
| Input | 24 tutorial movies, `movies.star` sha256 `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041` |
| Options | `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --ingest nvcomp` |
| Wall scope | whole process, wrapper-inclusive, including every requested report and the writer drain |

This is **not** the venue of the PR130 (SCARF A100-40GB) or PR128 campaigns. Nothing
here may be pooled with them.

Full machine-readable provenance, including the per-arm binary hashes and every input
hash, is in [`data/provenance.json`](data/provenance.json).

## Arms

Each arm is an independent clean build of one commit, so each mechanism is measured on
its own rather than inferred by subtraction from a combined figure.

| arm | commit | mechanism added |
|---|---|---|
| `a0_main` | `c499b1d3` | current main |
| `a1_base` | `5d0eb5c` | + PR130 workspace + PR131 dose plane — **the branch parent** |
| `a2_gain` | `bc695da` | + worker-lifetime device-gain retention |
| `a3_premask` | `2dfcc14` | + static defect premask cache and sparse defect traversal |
| `a4_globalpool` | `fa3f18a` | + pooled global cuFFT plans, work area and inverse tile |
| `a5_patchpool` | `5bdd119` | + pooled batched patch R2C plan |
| `a6_final` | `a118699` | + pooled dose-weighted C2R plan, retained-byte accounting |

## Wall clock

![Whole-process wall by arm](charts/arms.png)

5 repetitions per arm, interleaved round-robin with the order reversed on alternate
repetitions so monotonic drift cannot favour one arm. 35 clean runs retained.

| arm | median | min | max | IQR | CPU-s | vs `a1_base` |
|---|---|---|---|---|---|---|
| `a0_main` | 13.634 | 13.044 | 14.499 | 0.865 | 20.44 | — |
| `a1_base` | 12.312 | 12.095 | 13.534 | 0.420 | 18.52 | reference |
| `a2_gain` | 11.662 | 11.489 | 12.057 | 0.212 | 17.54 | +5.28% |
| `a3_premask` | 10.048 | 9.920 | 10.257 | 0.285 | 15.93 | +18.39% |
| `a4_globalpool` | 9.857 | 9.824 | 10.848 | 0.115 | 15.91 | +19.94% |
| `a5_patchpool` | 9.794 | 9.475 | 10.485 | 0.379 | 16.49 | +20.45% |
| `a6_final` | 9.678 | 9.434 | 9.740 | 0.189 | 15.59 | **+21.40%** |

**This branch's result is `a1_base` → `a6_final`: 12.312 → 9.678 s, a 21.40% reduction.**
Paired within each repetition: +2.635, +3.826, +2.743, +2.662, +2.942 s, median paired
saving **2.743 s, 5/5 faster**.

`a0_main` → `a6_final` is 29.02%, but that figure includes PR130 and PR131 and must not
be attributed to this branch.

### Where the time actually comes from

| mechanism | median saving | share of the 2.634 s |
|---|---|---|
| device-gain retention | +0.650 s | 24.7% |
| **premask + sparse defect traversal** | **+1.614 s** | **61.3%** |
| global plan pool | +0.191 s | 7.3% |
| patch plan pool | +0.063 s | 2.4% |
| dose-weighted plan pool | +0.117 s | 4.4% |
| *three plan pools together* | *+0.370 s* | *14.0%* |

Two things follow, and they matter more than the headline.

**The premask commit carries most of the win and costs no retained VRAM.** It is also
the commit with the exactness risk (RNG draw order, traversal order), which is why its
equivalence was established separately and not inferred from the wall clock.

**The three cuFFT plan pools buy 0.370 s and cost the entire 269.53 MiB of retained
residency.** The individual pool steps (+0.191, +0.063, +0.117 s) are smaller than the
run-to-run IQR of the arms they sit between and are **not individually resolvable** at
n=5. Their *sum* is resolvable: `a3_premask` ranges 9.920–10.257 s and `a6_final` ranges
9.434–9.740 s with no overlap. Treat the three pools as one 0.370 s mechanism, not as
three separately justified ones.

## Memory and CPU

![Memory and CPU per arm](charts/mem.png)

| quantity | `a1_base` | `a6_final` | delta |
|---|---|---|---|
| median CPU-seconds | 18.52 | 15.59 | −2.93 |
| peak host RSS | 0.541 GiB | 0.553 GiB | +12 MiB |
| peak device memory (nvidia-smi, 100 ms sampling) | 3521 MiB | 3595 MiB | +74 MiB |
| pinned staging reservation | unchanged | unchanged | 0 |
| **retained across movies** | 0 | **269.53 MiB** | **+269.53 MiB** |

Retained residency breaks down as global workspace 56,986,624 B, inverse tile
56,986,624 B, patch plan 54,710,784 B, DW plan 56,986,624 B, device gain 56,955,920 B.
The binary reports it on the `Peak VRAM:` line each movie.

Sampled device peak rises by only 74 MiB because the retained buffers largely replace
allocations the base arm was making and freeing per movie; the retained figure is what
is *held between* movies, which is the quantity a VRAM budget has to respect.

The device peak is a 100 ms **sampled** peak, not an allocator high-water mark. The
retained figure is reported by the binary, not sampled.

## GPU occupancy

![GPU occupancy inside the profiled trace](charts/gpu.png)

From `nsys --trace=cuda,nvtx`, one capture per arm. Busy is an interval union over
kernel **and** copy together, measured inside the same capture that defines the span —
not derived by subtracting profiled device time from an unprofiled wall.

| | `a1_base` | `a6_final` |
|---|---|---|
| traced span | 15.428 s | 11.349 s |
| kernel union | 3.058 s | 3.061 s |
| copy union | 1.174 s | 0.564 s |
| busy union | 4.232 s (27.4%) | 3.625 s (31.9%) |
| kernel launches | 24,990 | 24,875 |
| H2D | 4.62 GB | 3.31 GB |

**Kernel time is unchanged** — 3.058 vs 3.061 s. None of these mechanisms makes the GPU
compute faster; they remove host work and host-to-device traffic. The GPU remains idle
roughly two thirds of the span, so this release does not address the dominant
inefficiency recorded in the earlier execution profile.

The H2D drop independently confirms the gain mechanism: 4.62 − 3.31 = 1.31 GB, against
56,955,920 B × 23 avoided re-uploads = 1.310 GB.

Profiled spans are inflated by CUPTI and are not production walls. Only the comparison
between the two arms is meaningful.

## Host stages

![Host wall by pipeline stage](charts/stages.png)

From `nsys --trace=nvtx,osrt`, one capture per arm, no CUDA trace so CUPTI does not
inflate the CUDA-heavy stages. NVTX ranges unioned over all 24 movies.

| stage | base | final | delta |
|---|---|---|---|
| `MOVIE (executeOwnMotionCorrection)` | 12.839 | 10.070 | −2.769 |
| `fix defect` | 1.758 | **0.019** | **−1.739** |
| `detect hot` | 0.950 | 0.689 | −0.261 |
| `prep patch` | 0.260 | 0.103 | −0.156 |
| `dose weighting` | 1.387 | 1.346 | −0.042 |
| `logfile pdf` | 1.184 | 1.143 | −0.041 |
| `patch align` | 1.207 | 1.386 | **+0.180** |
| `global alignment` | 0.338 | 0.367 | +0.030 |

`fix defect` collapsing from 1.758 s to 0.019 s is the premask cache: the static mask is
built once instead of 24 times, and the replacement loop iterates the bad-pixel list
instead of scanning every pixel of every frame.

`patch align` is **0.180 s slower** in the final arm. This is one instrumented capture
per arm with no spread, so it is not separable from run-to-run variation at this
evidence level, and the unprofiled wall shows the opposite sign overall. It is recorded
rather than explained; if the plan pools are kept it is worth a dedicated paired
measurement, because a pooled plan making patch alignment slower would undercut the
0.370 s the pools are there to deliver.

Stages nest — an inner stage is also counted inside its parent — so the column does not
sum to the process wall. The async writer drain lies inside the process wall but inside
no NVTX range and cannot be read off this table.

## Flame graphs

![CPU flame graph, base](charts/flame-a1_base.png)

![CPU flame graph, final](charts/flame-a6_final.png)

`nsys --sample=process-tree --backtrace=fp`, 250 µs sampling, main thread.
18,293 samples over 1,301 unique stacks for the base arm; 14,876 over 1,116 for the
final arm. The sample-count ratio tracks the wall ratio, which is the expected shape
for a host-bound reduction.

CPU sampling inflates host-side CUDA API intervals substantially; these graphs are for
*where* host time goes, not *how much*. The wall numbers above come from unprofiled
runs.

## Product equality

The composition's exact-output gate against main is reported in the branch's own
validation, not here: complete non-PDF tree, 24 MRC images, 25 STAR files,
341,735,520 pixels per arm, status PASS, 0 different files, with PR131's declared
`--allow-added-log-line 'Peak VRAM:'` in force. Every profiled run in this campaign was
graded too — 24 global, 600 patch and 24 DW witnesses, 24 nvCOMP ingest witnesses, zero
warnings and 109 product files in all six captures — so no instrumented run silently
degraded.

## Integrity of the measurement

The box is shared. The campaign records the payload PID and flags any other process on
any device; two runs were caught with a co-tenant present, discarded and re-run. The
35 retained runs have zero foreign PIDs.

An earlier version of this harness flagged co-tenants by **GPU UUID mismatch**, which
cannot see a neighbour on the *same* GPU — the uuid matches. Two contaminated
observations passed that check before it was corrected to compare PIDs. Those
observations are not in this dataset; the discarded v1 campaign is retained at
`campaign-contaminated-v1/` on the host.

## Limits

* One venue, one device, one input set. No cross-venue or cross-geometry claim.
* Genuine cross-device retirement and execution is **UNRUN**: `gpu_id` is a single
  process-wide value, so no two-device path exists to exercise.
* The three plan-pool steps are not individually resolvable at n=5; only their sum is.
* `patch align` regressing by 0.180 s rests on a single instrumented capture per arm.
* Device peak is sampled at 100 ms, not an allocator high-water mark.
* Flame graphs and stage walls come from instrumented runs and are not production walls.
* PDFs are inventoried, not content-compared.
* No scientific-truth claim. Same-backend byte equality is not CPU-backend or
  scientific equivalence.

## Reproducing

Tools used are committed under [`tools/`](tools/) in this directory:
`campaign.py` (interleaved timed arms with co-tenant detection), `capture.sh` (the six
nsys captures), `prof_json.py` (per-capture extraction — one capture per JSON, no
cross-run arithmetic), `analyze_all.sh` and `mkcharts.py` (charts, one time domain
each).

NVTX annotation uses `tools/nsys_analysis/patch_nvtx.py` from PR132, which required
repair before it would patch current source at all: two of its four anchors were pinned
to `1d7e13f`, and the per-movie replacement body re-emitted the old
`executeOwnMotionCorrection(Micrograph&)` signature so a patched tree failed to compile.
Its gates were bare `assert` and vanished under `python -O`. Those fixes are in PR132,
not here.

Raw `.nsys-rep` and `.sqlite` captures are not committed — 8–18 MB each. They are
retained on the host at `/home/alex/mc-release-20261002/prof/`.
