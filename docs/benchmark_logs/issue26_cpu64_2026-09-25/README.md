# Issue #26 CPU strong-scaling measurements — cpu64, 2026-09-25

Raw artifacts behind [`docs/cpu_scaling_issue26.md`](../../cpu_scaling_issue26.md).
Host `small-refmac-machine` (ssh alias `cpu64`), AMD EPYC 7763, 64 vCPU,
2 sockets / 2 NUMA nodes, 226 GiB, KVM guest. Source commit
`3e3a19679337d3de61327c02eef1a2947cf13517`, built `-O3 -DNDEBUG -std=gnu++17
-fopenmp` with gcc 13.3.0 and FFTW 3.3.10.

## Arms

| file | what |
| :-- | :-- |
| `A_patch5x5_unbound.json` | strong scaling j=1,2,4,8,16, 5x5 patches, default affinity, 3 reps |
| `B_patch5x5_spread.json` | same with `OMP_PROC_BIND=spread OMP_PLACES=cores` |
| `C_global_unbound.json` | same, global-only (`--patch_x 1`), 2 reps |
| `D_patch5x5_numalocal.json` | `numactl --cpunodebind=0 --membind=0`, j=8,16 |
| `E_pab_global_j1.json` | paired baseline vs candidate, global-only, j=1, 6 pairs |
| `F_pab_global_j8.json` | same at j=8 |
| `G_pab_patch5x5_j8.json` | same at 5x5 j=8 — the no-op control |
| `H_tp_base_global.json` | 24-movie throughput, baseline, global-only, 16-core budget |
| `I_tp_cand_global.json` | same, candidate |
| `J_tp_base_patch5x5.json` | same, baseline, 5x5 |
| `K_tp_base_global_spread.json` | same with affinity — shows the multi-process binding trap |
| `L_patch5x5_close.json` | `OMP_PROC_BIND=close OMP_PLACES=cores` |
| `M_patch5x5_placesonly.json` | `OMP_PLACES=cores` alone |
| `N_j4_unbound_x10.json` | j=4 x 10, unbound — placement-lottery distribution |
| `O_j4_spread_x10.json` | j=4 x 10, bound |
| `P_m30_unbound.json` | movie `20170629_00030`, j=1,4,16, unbound — does the 00021 curve generalise? |
| `Q_m30_spread.json` | same, bound |

`run_all.log`, `run_affinity.log` and `run_m30.log` are the drivers' own logs, including every
settle wait and its observed `load1`.

## Reading the JSON

Each run records wall/user/sys/maxrss, the `--j` value, its position in the
interleaved order, per-stage `-DTIMING` timings, output pixel and core-header
digests, and a `contention` block. In `contention`, `foreign_cores_*` is
third-party CPU sampled once per second **excluding this session's own process
tree** (the measured binary is a grandchild via `/usr/bin/time`, so a naive
parent-pid exclusion counts your own workload as foreign load — an earlier
version of the harness did exactly that and was discarded). `own_cores_*` is the
same figure for our own tree. Both come from `ps pcpu`, which is a lifetime
average, so they are average-over-run values, not instantaneous.

Two foreign `ctffind` processes belonging to another user held a flat ~2.0 of 64
cores for the whole session; that is the `foreign_cores_mean ≈ 2.0` baseline.

## Harness

`harness/` holds everything needed to reproduce:

| file | what |
| :-- | :-- |
| `bench26.py` | scaling sweep: flock-gated, settle gate, contention sampler, interleaved order |
| `paired_ab.py` | paired A/B with arm order alternating within each pair; recovers positional bias |
| `throughput.py` | whole-dataset throughput at a fixed core budget across process/thread layouts |
| `analyze.py` | renders the tables in the write-up |
| `controls2.c` | hardened machine-ceiling kernels (`fma`, `exp`) — the controls that separate machine scaling from MotionCorr's |
| `controls.c` | first-pass controls including STREAM-triad bandwidth and FFTW plan-per-call comparison |
| `fftw_lock_stats.{h,cpp}`, `patch_lock_instr.py` | diagnostic instrumentation that measures wait and hold time on `#pragma omp critical(FourierTransformer_fftw_plan)`; the patcher inserts probes at all six sites |
| `run_all.sh`, `run_affinity.sh`, `run_movie30.sh` | the three series drivers |

The instrumentation is **diagnostic only** and is deliberately not part of the
build. Apply it to a scratch copy of the tree:

```
python3 harness/patch_lock_instr.py <scratch-src>   # after copying the two .h/.cpp in
cmake -S <scratch-src> -B build-instr -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CXX_FLAGS='-DTIMING -DFFTW_LOCK_STATS'
```

Note when copying a configured build tree between source directories: CMake
caches an absolute `CMAKE_HOME_DIRECTORY`, so `cp -r src-a src-b && make -C
src-b/build` rebuilds **src-a's** sources and silently produces an identical
binary. Configure a fresh build directory instead.
