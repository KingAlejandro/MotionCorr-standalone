# Lane B, GPU regime: 4/3/2/1 concurrent single-GPU workers

Source `caf0375`. SCARF `gn3003.scarf.rl.ac.uk`, partition `gpu-devel`,
`--exclusive --constraint=scarf23`, Slurm job 3512587. 64 CPUs,
4x NVIDIA A100-SXM4-80GB, `transparent_hugepage = [always]`. CUDA 12.8,
g++ 11.5, `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DTIMING=ON`,
`-DCMAKE_CUDA_ARCHITECTURES=80`.

GPU UUIDs, recorded because ordinals do not identify silicon:

```
0  GPU-a62fc306-8b33-aea3-4032-b84c60b48994
1  GPU-1da51bec-2aa1-f3cf-0839-e8288d3caea3
2  GPU-adc69069-d9e2-a9e7-4029-5d0a8f3b0941
3  GPU-b1d53075-e1b1-6619-7c73-5e03e9205326
```

## What "W GPUs" means here

Main's runner takes only the **first** id from `--gpu`
(`gpu_id = textToInteger(allThreadIDs[0][0])`), so one process drives one
device; in-process multi-GPU is unmerged PR #106. W GPUs is therefore W
concurrent processes over contiguous shards of the 24 movies (6/8/12/24 each),
each with `--gpu <i>` and its own `taskset` slice.

**The aggregate CPU budget is fixed at 24 logical CPUs for every W** — 6, 8,
12 and 24 per worker at W = 4, 3, 2, 1. That is deliberate: the program's
multi-GPU section says `--max_io_threads` has to be read against the whole
allocation rather than multiplied per worker, and lane B's motivating
hypothesis is specifically that persistent handles relieve CPU-side
contention when several GPU workers compete for one decode budget. Giving
each worker its own 24 CPUs would confound W with total CPU and would remove
the very contention the experiment is about.

Data staged to node-local `/tmp` (3.1 GB); page cache warmed identically
before every configuration; 5 reps; arm order alternating between reps.

Raw records: `gpu_ab_scarf.jsonl`.

## Guards

Every configuration must produce 24 corrected images, and an `on` arm must
show `Persistent TIFF readers: N` in **24 of 24** per-movie logs while an
`off` arm shows it in **0**. A violation aborts the job rather than emitting a
plausible number. All 40 configurations passed: `rc=0`, 24 images, engagement
correct in every arm.

This guard earned its place. The first attempt at this sweep (job 3512586)
ran correctly but used absolute movie paths, so the runner mirrored the whole
input path under the output directory and every product landed where the
counters did not look. It reported `movies_out=0, pool_logs=0` for all 16
configurations. Those runs' wall times were real but unattributable to arms,
and were discarded rather than quoted.

## Result

| GPUs (W) | CPUs/worker | off median (s) | on median (s) | on − off | off spread | throughput vs W=1 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 24 | 17.63 | 17.45 | −1.0% | 0.47 | 1.00x |
| 2 | 12 | 10.98 | 11.07 | +0.8% | 0.34 | 1.61x |
| 3 | 8 | 8.75 | 8.84 | +1.0% | 0.18 | 2.01x |
| 4 | 6 | 8.27 | 8.12 | −1.8% | 0.20 | 2.13x |

Pooled over all W: off mean 11.41 s, on mean 11.38 s, **−0.3%**.

Per-W the difference is 0.6–2.0 within-arm standard deviations and **alternates
sign** with W. There is no consistent effect.

**This is the sharpest available refutation of lane B's premise.** The
hypothesis was that persistent handles would pay once several GPU workers
contend for one CPU decode budget. That contention is visible here —
throughput saturates at 2.13x for 4x the GPUs, because 24 CPUs is the binding
constraint, not the devices — and the pool does not relieve it.

### Parity

All 39 non-reference configurations against `w1_off_r1`: **24 images compared,
0 mismatches** each, comparing from byte offset 1024. Zero `PIXELS DIFFER` and
zero `MISSING` lines across the whole run.

## Stage attribution on the GPU host, and the THP question

The same benchmark on the same node (THP `always`) against cpu64 (THP
`madvise`) turns an inherited caveat into a measurement.

| stage | cpu64, THP=madvise | gn3003, THP=always | ratio |
|---|---:|---:|---:|
| strip decode | 0.6394 | 1.9559 | 3.06x |
| allocation + first touch | 0.6317 | 0.1178 | **0.19x** |
| conversion + Y placement | 0.0951 | 0.0904 | 0.95x |
| open + close | 0.0188 | 0.0123 | 0.65x |
| layout (IFD walk + tags) | 0.0043 | 0.0031 | 0.72x |
| directory selection | 0.0007 | 0.0006 | 0.76x |
| **in-path total** | **1.3900** | **2.1800** | |
| **removable lifecycle** | **0.0239 (1.7%)** | **0.0159 (0.73%)** | |

Two things change between hosts, in opposite directions.

**Allocation and first touch is 5.4x cheaper under THP `always`** — 0.632 s to
0.118 s — which confirms that the "45% of a movie read" figure from cpu64 is a
property of that host's THP setting and must not be carried across hosts. It
is 5.4x here, not the ~40x seen on other workloads, but the direction and the
scale of the caveat hold.

**Single-threaded strip decode is 3.1x slower** on the EPYC GPU node than on
cpu64, so the in-path total is larger there despite the cheaper allocation.

The two effects together make the lifecycle a persistent pool can remove
**0.73% of a movie read on the actual GPU host** — less than half its share on
cpu64, and in the regime where issue #85 expected ingest to matter most.

`raw_pread` is 0.0885 s on cpu64 and 0.0173 s on gn3003, and is excluded from
the total in both: LibTIFF mmaps the file rather than issuing those reads, so
it is not a storage floor that composes with the decode.

## Limitations

- Node-local `/tmp`, warm cache. Not PanFS. Open cost is storage-dependent and
  is the one term that could favour the pool elsewhere.
- Sharded single-GPU processes, not in-process multi-GPU. When PR #106 lands,
  a worker sharing one process with others may contend differently.
- 24 movies is a small dataset for a 4-GPU run: W=4 gives each worker 6
  movies, so per-worker startup is a larger share of the wall than it would be
  on the #73 corpus.
