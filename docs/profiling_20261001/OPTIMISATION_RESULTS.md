# Acting on the profile: two measured changes

Follow-on to [`../single_gpu_execution_profile.md`](../single_gpu_execution_profile.md).
Venue identical: `4GPUs`, A100 80GB PCIe `GPU-eddb42fe`, CPU mask `96-103`, THP `madvise`,
CUDA 12.8, nvCOMP 5.3, Release/sm80, 24 tutorial movies, `--j 8`.

Baseline here is **`a294f3b`** (tip of `experiment/post128-alignment-sync`), not `main`.
That branch is 197 commits ahead of the profiled baseline `1d7e13f`, which is what this
campaign labelled `main`. Against current main `c499b1d` the distance is 23 commits.
It already contains PR130's per-movie alignment workspace reuse and the separate
alignment-sync experiment. The main report's `patch align` figures, 4.21 s at
`1d7e13f` and 1.63 s at `abd6827`, belong to that earlier capture campaign. They
are not measurements of this `a294f3b` baseline or attribution of PR130's gain.

Raw data: [`data_opt/`](data_opt/).

## 1. OpenMP waiting policy — no code change

36 runs, paired within round, arm order alternated per round. One output digest across
all 36, so the policy does not perturb the numerics.

| arm | wall | CPU-seconds |
|---|---|---|
| nvcomp, `OMP_WAIT_POLICY=PASSIVE` | −0.005 s, 3/6 pairs faster | **−3.42 s, −18.0 %, 6/6 lower** |
| nvcomp, `GOMP_SPINCOUNT=1000` | +0.012 s | −3.57 s, −18.9 %, 6/6 lower |
| float (host decode), PASSIVE | +0.084 s | −2.59 s, −3.4 %, 6/6 lower |

PASSIVE buys ~18 % of the CPU-seconds on the nvCOMP path at no wall cost. The
host-decode path gains 3.4 % and is marginally slower on wall, so this belongs in the
GPU run script, not in a global default. `GOMP_SPINCOUNT` is equivalent; prefer the
documented variable.

The freed CPU only pays if something else consumes it, which is the multi-worker
question and is not tested here.

## 2. Worker-lifetime device gain — `perf/nvcomp-next`

`CudaMovieSession` is per movie, so `d_gain` was allocated, uploaded and freed once per
movie. Trace: **24 copies × 56,955,920 B, 719.5 ms, 98.5 % of all pageable H2D** in the
nvCOMP arm; `gain.mrc` is 3710×3838 float32 = 56,955,920 B exactly.

Retained in a `thread_local` pool keyed on (generation, nx, ny, device), where the
generation comes from the runner's existing `gain_cache` refill. 2×2 against the OpenMP
arm, round-robin, order reversed on even rounds, paired n=6:

| arm | wall | CPU-s |
|---|---|---|
| baseline, default OMP | 11.890 s | 19.07 |
| baseline + PASSIVE | 11.814 s | 15.51 |
| gain retained, default OMP | **11.316 s** | 18.37 |
| gain retained + PASSIVE | **11.278 s** | 14.81 |

Against baseline/default: gain retention **−0.530 s (−4.5 %), 6/6 pairs faster**;
both changes together **−4.7 % wall and −21.9 % CPU-seconds**. Effects are additive on
CPU-seconds (−0.70 + −3.56 = −4.26 measured −4.26) and roughly additive on wall.

An earlier two-arm run gave −6.8 % for the gain change. That baseline contained two slow
rounds; the 2×2 shares drift across four arms and supersedes it.

Cost: the device retains 54.3 MiB between movies. Host RSS unchanged.

### Exactness

Bit-identical MRC data sections and STAR files in every arm, with the ingest path
witnessed per movie by `--ingest_witness` rather than inferred from a matching digest:

| variant | witnessed | result |
|---|---|---|
| `--ingest nvcomp` / `compact` / `float` / `auto` | 24/24 each, as requested | exact |
| `--save_noDW`, `--group_frames 3`, `--first/--last_frame_sum`, no `--gainref` | each digest differs from default | exact |

`--bin_factor 2` exits 1 with no output on the **baseline** as well, so it cannot serve
as the geometry control.

### Not established

The geometry-change and changed-gain branches of the key are implemented but never
executed: the tutorial set has one geometry and one gain. Both need a synthetic fixture
before this is proposed for merge.
