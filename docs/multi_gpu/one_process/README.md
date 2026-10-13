# One process, several GPUs (`--use_own --gpu 0,1,2,3`)

One worker thread per listed device; workers take whole movies from the shared list.
Source: `src/` tree `63b6249a` (base `45b57754`), the same tree as this PR's commit.

## Identity (4GPUs, 2026-10-13)

Host `4-gpu-vm`, `flock /tmp/motioncorr-bench.lock taskset -c 96-103`, CUDA 12.8, sm_80,
Release. Binaries: candidate `4a3b7337137924af`, no-mutex control `5831463a58ec3a96`
(sha256 prefixes). Input: the 24 tutorial movies (`movies.star` sha256 `fb998f70…`).
Common flags: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc`. Driver: [`evidence/series.sh`](evidence/series.sh),
[`evidence/identity.py`](evidence/identity.py); console in [`evidence/series.out`](evidence/series.out).

| Arm | Command | Compared with `single` |
|---|---|---|
| single | `--gpu 0 --j 2 --seed 1` | reference |
| multi | `--gpu 0,1,2,3 --j 8 --seed 1` | products identical (0 differences) |
| nomutex (negative control) | as multi, built without the defect-RNG lock | 29 files differ, products of 4 movies |
| seed2 (negative control) | `--gpu 0 --j 2 --seed 2` | products of 5 movies differ |

Comparison tool: `docs/issue85_laneC/compare_output_trees.py` with the 24-movie manifest
(MRC bytes excluding the header timestamp, normalised STARs, EPS).

- Products only (`--products-only`), single vs multi: `Validated 24 movies, 24 MRC images,
  25 STAR files, 341735520 pixels per arm / Comparison: products; status=PASS; different files=0`.
- Full tree, single vs multi: FAIL on three per-movie logs only (movies 00022-00024), and
  `different_products` is empty ([`evidence/runs/cmp-single-multi.json`](evidence/runs/cmp-single-multi.json)).
  The differing lines are device-memory diagnostics: free memory at start (77938 vs 77942 MiB)
  and the "rose by at most" figure (156 vs 160 MiB). These movies were the first on a fresh
  device in the multi arm; the chunk size is unchanged. The 4-process launcher shows the same
  difference on each device's first movie.
- Device witness: in the multi arm a single PID held compute contexts on all four GPU UUIDs, no
  foreign process was on the GPUs, and the per-movie `Device: N` log lines show 6 movies on
  each of devices 0-3 ([`evidence/runs/summary.json`](evidence/runs/summary.json)).
- The no-mutex control shows that concurrent workers do race on libc `rand()` in defect
  replacement; with the lock held from seeding to the last draw, each movie's values match the
  serial run.

The wall times in `summary.json` (single 26.9 s, multi 12.7 s) use different `--j` and one run
each; they are not a speed comparison.

`ctest -L hardware` on the same host and tree (BUILD_TESTING=ON build, binary
`48292ddf07900234`): 28/28 passed. These tests are single-device; they cover regressions in the
shared CUDA paths, not the multi-device mode.

## Timing (SCARF, 2026-10-13)

**Result: one process x 4 devices is slower than 4 processes x 1 device on this node.**
Median +0.48 s on a 6.67 s wall; the one-process arm was faster in 0 of 12 pairs.

Venue: SCARF `gn0006`, exclusive allocation (job 3599986), 4x A100-SXM4-40GB, all 64 CPUs,
THP `always`. Binary sha256 prefix `5cf08e1592a3d17a` (same `src/` tree).
Input: the 96-movie list (24 tutorial movies x 4). Arms:

- T: one process, `taskset -c 0-31 ... --gpu 0,1,2,3 --j 32` over all 96 movies.
- P: four processes, one per 24-movie shard. Each process has `CUDA_VISIBLE_DEVICES=<UUID k>`
  and runs `--gpu 0 --j 8`, pinned to the 8-CPU NUMA-local lane k (0-7, 8-15, 16-23, 24-31).

Both arms use the same 32 CPUs and `--ingest nvcomp --skip_logfile`.

Pairs were interleaved, with alternating order, after a discarded warm-up pair.
Driver: [`evidence/scarf/timing.py`](evidence/scarf/timing.py); results in
[`timing.json`](evidence/scarf/timing.json) and [`timing.out`](evidence/scarf/timing.out).

| | T (1 process) | P (4 processes) |
|---|---|---|
| Wall, median (range), 12 pairs | 7.144 s (7.028-7.372) | 6.667 s (6.515-6.781) |
| T - P, median (range) | +0.482 s (+0.362 to +0.769) | |
| Max RSS | 1.48 GB | 4 x 0.39 GB |
| Peak VRAM per device | 3364 MiB | 3208-3364 MiB |

Order does not explain the gap: the median T - P is +0.494 s when T ran first and +0.482 s when
P ran first. The witness showed one PID on all four GPU UUIDs in T and four distinct PIDs in P.

Diagnosis ([`evidence/scarf/diag.py`](evidence/scarf/diag.py), 6 pairs per condition):

- With 4 movies (one per GPU), T - P is +0.342 s (range +0.282 to +0.376), so most of the loss
  is fixed per run.
- With 96 movies and `OMP_WAIT_POLICY=passive`, T - P is +0.549 s, so OpenMP spin-waiting is
  not the cause.

nsys trace of the 4-movie run (`--trace=cuda,osrt`; [`evidence/scarf/prof.sh`](evidence/scarf/prof.sh),
API summaries in [`evidence/scarf/nsys/`](evidence/scarf/nsys/)). nsys inflates the absolute
walls, so only the comparison between arms is meaningful. Within one process the CUDA driver
serialises work that runs in parallel across processes:

- Context creation: each T worker spends 490-585 ms in about 440 driver ioctls, and the large
  ioctls finish in lockstep across the four threads (35-40 ms each). Each P process spends
  about 390 ms on the same work, and the four processes run concurrently. The workers start at
  265 ms; their first CUDA call is at about 1010 ms. A P process reaches its first CUDA call
  about 520 ms after launch.
- Pinned host memory: the four 70 ms `cudaHostAlloc` calls run one after another in T (total
  448 ms vs 273 ms). They also hold the address-space lock, and one worker's `mmap` waited
  60 ms behind another thread's pinning. `cudaFreeHost` at exit is serialised the same way
  (201 vs 113 ms).
- `cudaMalloc`/`cudaFree` total 148/145 ms in T against 19/24 ms in P (longest single
  `cudaMalloc` in T: 75 ms). The longest `cuMemGetInfo` in T took 59.6 ms; in P it is
  close to 0.

The motive for this change was that context creation is serialised across processes
(measured earlier on `gn0005`). That did not reproduce on `gn0006`, where the four processes
create their contexts concurrently. The cost of in-process serialisation is therefore not
offset by any saving.

Conclusion: for throughput, keep the 4-process launcher (`tools/multi_gpu/run_multi_gpu.py`).
The one-process mode is correct (see Identity), and its only advantage is that it has the
same process shape as RELION's accelerated branch.
