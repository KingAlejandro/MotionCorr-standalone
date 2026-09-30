# Phase 1: static process-per-GPU sharding on post-#128 main

Source `c07b1277f62b9aab09c6d53276b4b091ec110ff4` (branch `experiment/post128-multigpu`,
main `c499b1d` + the #117 harness port). Nothing is merged.

## Result

Products are byte-identical to the serial baseline at 1, 2 and 4 workers.
2 GPUs is worth taking; the 4th GPU is not, on this workload.

| GPUs | median wall | vs 1 GPU | efficiency | spread (5 reps) | cores busy / 32 |
|-----:|------------:|---------:|-----------:|----------------:|----------------:|
| 1 | 12.03 s | ×1.00 | 100 % | 0.18 s | 4.37 |
| 2 | 6.97 s | ×1.73 | 86.3 % | 0.24 s | 4.61 |
| 4 | 6.04 s | ×1.99 | 49.8 % | 1.78 s | 7.10 |

Going 2 → 4 buys ×1.15 and multiplies the run-to-run spread by seven.

## Venue

SCARF `gn3002`, exclusive, 4× A100-SXM4-80GB, 2× AMD EPYC 7302, 32 physical
cores with SMT2, 8 NUMA nodes, THP `always`, CUDA 12.8.61, nvcomp 5.3.0.16,
input on `/work4/scd` (PanFS). This is the Phase 0 baseline venue, not the #128
campaign's (which was A100-40GB, 32 CPUs, THP `madvise`); the two must not be
pooled.

Fixed budget: the 32 physical cores `0-31`. On this node `cpu N` and `cpu N+32`
are SMT siblings, so `0-31` is one thread per core and no arm contends with
itself. Masks follow the GPU NUMA affinity from `nvidia-smi topo -m`
(GPU0→node3, GPU1→node1, GPU2→node7, GPU3→node5; nodes 0-3 are socket 0), so
each worker holds its own GPU's NUMA node on that GPU's socket. Per-worker `--j`
and `OMP_NUM_THREADS` are set to the mask width.

The 1-GPU arm is the exception and cannot be fixed: holding the budget at 32
gives its single worker both sockets, so half its cores are remote to GPU 0.

## Correctness

All three arms produce 24 MRC, 25 STAR and 341,735,520 pixels identical to the
serial baseline, `different_products: []`, via
`docs/issue85_laneC/compare_output_trees.py --products-only` against a pinned
movie manifest and input-STAR hash.

This works because `init_random_generator(seed)` runs per movie inside
`executeOwnMotionCorrection` (`src/motioncorr_runner.cpp:2239`) and `srand`
resets the single stream that both `rand()` and `rnd_gaus()` draw from, so a
movie's hot-pixel replacements do not depend on which movies preceded it in the
same process.

Controls, all required before the equality above is readable:

- **Comparator is live.** An unmutated copy of the baseline passes; one flipped
  payload byte in one movie is reported as `DIFF`. The copy needs its joint
  STAR rewritten first — `cp -a` carries absolute paths, and without the rewrite
  both legs are rejected for referencing the original root and neither observes
  a pixel.
- **Venue is stable.** A repeat of the exact Phase 0 configuration gives 12.71 s
  against the recorded 12.89 s, and its products are byte-identical to the
  baseline.
- **Pinning is witnessed, not asserted.** Every worker's mask is read back from
  `/proc/<pid>/status`: `MATCH` on all of them, observed as `0-31`;
  `0-15`,`16-31`; `8-15`,`0-7`,`24-31`,`16-23`. Budget covered 32/32, disjoint.
- **Devices are witnessed.** `all_pids_witnessed_on_intended_distinct_devices`
  true on every arm, by UUID from `nvidia-smi` compute-apps samples.

Tests at this head: ctest 40/40 (39 on main plus `MultiGpuScheduling`),
collection gate PASS, `MultiGpuScheduling` 50/50, `OutputTreeComparator` 17/17.

## Where the limit is not

The CPU budget is not binding. No arm exceeds 7.1 busy cores of 32, and in the
4-GPU arm each worker averages 1.4–1.9 running threads against an 8-core mask.
The fixed-budget design was enforced exactly and turned out to constrain
nothing, so these numbers are not a CPU-starvation result.

The 1-GPU arm spends 52.0 CPU-seconds against the 2-GPU arm's 31.1 for the same
work. `--j 32` returns ~0.7 s of wall over the baseline's `--j 8` (12.03 vs
12.71) for ~20 extra CPU-seconds, consistent with OpenMP spin-wait across 32
threads. Widening a single process is not the direction.

Amdahl does not fit: (T1, T2) implies a 1.91 s serial part and predicts 4.44 s
at 4 GPUs against 6.04 s measured. Something degrades specifically at 4
workers. The final-worker tail is only 0.56 s of 6.04 s, so it is mostly not
load imbalance, and 24 movies over 4 workers is 6 each, so per-process CUDA
startup is a large fraction of the run.

Candidate causes, **not measured here**: concurrent TIFF reads contending on
PanFS, and fixed per-process startup that 6 movies cannot amortise. The 1.78 s
spread at 4 GPUs against 0.24 s at 2 is consistent with shared-filesystem
contention but does not establish it. Distinguishing them needs an I/O-wait
measurement and a run with input on local scratch.

## Limitation

24 movies is small for 4 GPUs. The 49.8 % figure is a property of this workload
at this size, not of process-per-GPU sharding: a dataset large enough to
amortise per-process startup would move it. Do not quote it as the scaling limit
of the approach.

## Evidence

- `evidence/p1_multigpu_3516247.log` — full job output
- `evidence/p1_campaign_points.txt` — the 15 campaign points
- `evidence/p1_equality.txt` — the three equality reports
