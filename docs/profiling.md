# Profiling kit (`tools/profiling/mcprof.py`)

The standard way to measure a MotionCorr build and to judge an A/B performance
claim. One command per question; every output records where its numbers came
from; the instruments are kept apart. Python 3.9+ standard library only (no
numpy). CTest `ProfilingKit` runs its tests without a GPU.

```
mcprof.py compare main=build-a/motioncorr cand=build-b/motioncorr \
    --data /path/to/data --work out/ab --cpus 96-103 --gpu-uuid GPU-<uuid> \
    --pairs 10 --profile-pass 3 --trace-pass 2 -- \
    --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
    --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp
```

Everything after `--` goes to MotionCorr unchanged. The kit adds `--i`,
`--o` and `--profile` itself, runs the payload from `--data` (so relative movie
paths in the STAR resolve and products land at `<out>/Movies/...`), pins it
with `taskset -c <cpus>` and selects the GPU with
`CUDA_VISIBLE_DEVICES=<uuid>`; pass `--gpu 0`. `--movies N` uses the first N
rows of the STAR through a staging directory of symlinks.

## Commands

| command | instrument | produces |
|---|---|---|
| `run ARM...` | unprofiled process | `runs.jsonl`, per-arm wall/CPU/RSS/faults/VRAM table |
| `compare A B [C...]` | `run`, paired and interleaved, plus identity; optional `--profile` and trace passes | verdict, identity, stage deltas, device deltas, a trace summary per arm |
| `trace ARM` | Nsight Systems | per-stage device busy/idle, copies, syncs, allocations, memory high-water, top kernels, `timeline.json` |
| `trace --from-sqlite F` | an existing export | the same analysis without a capture |
| `kernels ARM` | Nsight Compute | unit-filtered counters for named kernels, joined to nsys durations |
| `report DIR` | none | regenerates `report.md` (`--html` for a self-contained page) from stored results |
| `selftest` | none | the CTest suite |

Each invocation writes into a fresh `--work` directory: `provenance.json`,
raw results (`runs.jsonl`, `identity.json`, `profile/*.jsonl`,
`trace/<arm>/trace.json`, `kernels.json`), the derived `compare.json` or
`results.json`, and `report.md`. Run trees are deleted after use unless
`--keep-outputs`; `trace` keeps the `.nsys-rep` by default (`--keep sqlite`
also keeps the export).

## Trust rules and how they are enforced

1. **Provenance.** `provenance.json` holds the command, the kit commit (and
   whether it was dirty), per arm the binary path, SHA-256, linked CUDA/cuFFT/
   nvCOMP libraries and source commit, the host (CPU model, lane, load,
   clocksource, THP, `perf_event_paranoid`, nvcc release, relevant
   environment), the GPU by UUID (index, driver, CUDA, persistence, clocks),
   the locks and how long they took, the settle result, the input STAR hash
   and the exact payload options and environment. The source commit comes
   from `--commit`, else from the source directory recorded in the build's
   `CMakeCache.txt` (git, or a `SOURCE_COMMIT` file, labelled unverified). A
   binary hash identifies a build, not a source: MotionCorr builds are not
   reproducible.
2. **Instruments are not mixed.** Report sections each name one instrument in
   their first line, and no number is computed across sections. The verdict uses
   only unprofiled round runs; `--profile` passes are recorded in `runs.jsonl`
   with `kind: profile` and excluded from it (tested).
3. **Paired, interleaved A/B.** Each round runs every arm once; the order
   rotates (two arms: AB, BA, AB, ...), so each arm takes each position equally
   often. `--warmup` (default 1) runs each arm once first and discards it: an
   alternating order cancels position, not a cold binary or page cache. Before
   each round, and before each `--profile` and trace pass, the kit waits up to
   `--lane-wait` seconds (default 300) for the lane to drop to 0.25 busy cores;
   a timeout is recorded, not hidden. A run is flagged when a foreign process
   appears on the target GPU, the GPU was occupied at start, other processes
   used more than 0.25 cores of the lane on average, the payload's affinity
   differed from the lane, or the process image was not the arm's binary. A
   flag on any run discards the **whole round**: every arm loses it, so both
   arms always keep the same rounds and each retained difference is a complete
   pair (tested). The report lists rounds planned, retained and discarded,
   each discarded round with its order and the arm(s) that triggered it, and
   warns when one arm alone triggers most discards (the arm may cause the
   condition itself) or when the kept pairs lose their AB/BA balance.
   `--max-rounds N` runs extra rounds, up to N, until `--pairs` rounds are
   clean; stopping depends on the flags only, never on the timings, and every
   round run is recorded. `--profile` passes are never dropped; a flagged pass
   is named in the stage section.
4. **Identity on every comparison.** Round 1's product trees are compared
   before any timing is reported (below). A difference stops the comparison
   with exit status 2 and a FAIL in the report.
5. **Shared host.** The kit takes `/tmp/motioncorr-bench.lock` and
   `/tmp/motioncorr-gpu<index>-correctness.lock` with `flock` in its own
   process. The descriptors are close-on-exec, so payloads and samplers never
   inherit them, and the file is never deleted. After acquiring it checks that
   the path still names the locked inode (an unlinked lock file splits the
   mutex). It then waits up to `--settle-timeout` for the target GPU to be
   empty and no compiler (`cc1plus`, `nvcc`, `cicc`, `ptxas`, by exact name) to
   run, and records the wait. `--runner-cpus` keeps the kit's own sampler off
   the payload lane.
6. **Tested.** `tools/profiling/tests/` runs under CTest. The Nsight queries
   and metrics are checked against a SQLite fixture built on the schema
   captured from a real nsys 2024.6.2 export (`tests/fixtures/`), with
   hand-computed answers for union busy time, idle split at stage boundaries,
   sync census, allocations, copies, kernel counts and memory high-water. The
   statistics, identity rules, runner, locks and an end-to-end compare (null,
   slowed and product-difference arms against a stand-in binary) are tested
   too.

## What the numbers mean

### `run` (unprofiled)

- **wall**: `CLOCK_MONOTONIC` from spawn to reap of the payload process.
- **CPU, peak RSS, faults**: `wait4` rusage of the payload and every
  descendant it reaped (Ghostscript included). Peak RSS is the largest single
  process.
- **VRAM proc**: NVML per-process used memory for the payload's processes
  (session-id ownership), sampled every ~10 ms. It includes the CUDA context.
- **VRAM dev delta**: NVML device used memory minus the median of an idle
  baseline taken just before the run. Device used memory includes
  driver-reserved memory, which the baseline removes.
- Both VRAM figures are **sampled peaks, so lower bounds**. If NVML cannot be
  loaded the kit falls back to polling `nvidia-smi` and says so.
- **lane foreign CPU**: busy jiffies of the lane CPUs from `/proc/stat` minus
  the payload's own CPU time, per second of wall. Kernel work on those CPUs
  counts as foreign.

### Verdicts (`compare`)

For paired differences d = B − A (positive: B slower):

- **noise** = max(1.4826 × MAD(d), `--noise-floor`): the pair-to-pair scatter
  measured in the same series.
- The median of d gets a distribution-free confidence interval from binomial
  order statistics at ≥95%. It exists only from **6 retained pairs** up. With
  fewer, the verdict is "not resolved (N retained pairs, 6 needed)" and no
  noise or resolution is claimed (the 6-pair minimum is enforced in the
  verdict itself, not only through the interval). With 10 pairs it is
  [d(2), d(9)].
- **"resolved faster" / "resolved slower"** requires the interval to exclude
  zero and |median d| > noise.
- Otherwise **"not resolved (below noise X s)"**, X = max(noise, interval
  half-width): effects smaller than X are not distinguishable with this data.
- The report also gives the sign test, the paired IQR and range, and the
  positional cost: the median difference split by which arm ran second.

### Identity

- MRC: bytes 0–223 of the header, the extended header and the full payload
  must be identical. Bytes 224–1023 are the label block, where MotionCorr writes
  a timestamp.
- Every other file must be byte-identical after the tree's own absolute root is
  replaced by a placeholder (STAR and EPS embed the output path).
- Per-movie `.log` files (timing values) are excluded and PDFs (Ghostscript
  dates) are inventoried only. Inventories must match.
- At least one MRC must be compared; an empty comparison fails.

### Stage and device deltas (`--profile-pass N`, `--trace-pass N`)

`--profile-pass` (3 per arm when given without N) runs each arm under
`--profile`; `--trace-pass` (2 when given without N) traces each arm. Passes
alternate arm order. Each pass is one process; its value for a stage is the
median over its steady-state movies (all but the first). Movies within one
process share its conditions (memory placement, page cache, host load), so
they are not independent samples. The noise therefore comes from the spread of
pass values within each arm: pooled variance, df = Pa + Pb − 2, and a delta is
flagged when it exceeds t(0.999, df) × SE and an absolute floor (0.5 ms, 50
faults, one kernel/call/allocation). Deterministic counts flag on any change.
The report shows the threshold next to each delta. With one pass per arm the
deltas are shown without flags.

An earlier rule took the movies of a single pass as samples (3 robust standard
errors). In a main-vs-main null on 4GPUs it flagged 1 stage in the `--profile`
deltas and 2 in the trace deltas, which is why flags now need replicated
passes. With t(0.999, 4) = 8.6 for three passes, small stage changes may not be
flagged; flags locate a change, they do not decide it.

`--profile` itself perturbs the process (it samples clocks and rusage at every
boundary and, by default, turns on per-step CUDA timing events), so its walls
are not comparable with unprofiled walls. `--profile-device-timing off` passes
`--profile_device_timing 0` to the binary in the `--profile` passes; the
default stays `on`, so stage deltas keep their previous meaning.

### Trace

`nsys profile --trace=cuda,nvtx[,osrt] --cuda-memory-usage=true`, CPU
sampling off unless `--sample`. Stage ranges are the NVTX ranges that
`--profile` emits; without `--profile` the trace has whole-run figures only.

**Device timing mode.** `--profile` alone also turns on per-step CUDA event
timing in alignment and dose weighting, and every timed step is a host wait.
A trace of such a process overstates sync calls and device idle in those
stages. Trace passes (`trace` and `compare --trace-pass`) therefore pass
`--profile_device_timing 0` by default (`--trace-device-timing off`): stage
ranges and the stage profile stay, the device synchronises as in production.
`--trace-device-timing on` restores the old behaviour. The mode is recorded in
`provenance.json` (`trace_device_timing`, per arm), in each `trace.json`
(`capture.device_timing`) and in the report. A binary without the option
cannot turn timing off; the kit then records `on (binary has no
--profile_device_timing)` and compares such traces only with that caveat.
Support is decided by the binary's own help, `motioncorr --use_own --help`
(plain `--help` stops before the option list); only if that probe fails does
the kit fall back to scanning the binary for the option string. The method is
recorded per binary as `device_timing_detection`.

- **segments**: inside each movie, the top-level `--profile` stages (NVTX
  depth 1 under `movie`); small gaps between them are `movie: unattributed`;
  outside movies, `before first movie`, `between movies`, `after last movie`.
  The segments tile the traced window (first to last traced event).
- **busy**: union of kernel, memcpy and memset intervals clipped to the
  segment; overlapping work counts once. kernel and copy columns are the unions
  of each kind alone.
- **idle** = segment wall − busy. Every idle interval is split at segment
  boundaries, so each piece is charged to the segment it lies in.
- **sync calls**: blocking CUDA runtime/driver calls (device, stream and
  event synchronize, synchronous memcpy, free), charged to the segment where
  they start. **blocked idle** is host time inside those calls while the
  device was idle.
- **malloc/free**: `cudaMalloc`/`cuMemAlloc` and `cudaFree`/`cuMemFree`
  calls. **kernels**: kernels whose device start lies in the segment.
- **copies**: by direction and memory kind (Pageable, Pinned, Device) from the
  export's own enums; byte counts are invariant across captures, rates are not.
- **memory high-water**: live allocations from `CUDA_GPU_MEMORY_USAGE_EVENTS`,
  keyed by process, context, device and address. Repeated Device Static
  symbols are counted once; any other duplicate or unmatched free is an error.
  It covers traced allocations only (no context, no driver-internal memory),
  so it is below NVML's per-process figure.
- Steady-state columns are medians over movies after the first; the first
  movie is shown separately.
- `timeline.json` holds each movie's stages, kernels and copies in ms from the
  movie start. `--sample` adds `folded.txt` (kernel-mode frames prefixed `[k] `).

Host time inside a trace is inflated (about 2× in call-heavy stages, measured
for patch alignment), and CPU sampling inflates some calls by more than 10×
(`cuModuleLoadData`). Use `run` for wall and `--profile` for host stages.

### Kernels

`ncu --kernel-name-base function --kernel-name regex:^<name>$` per kernel, with
`--launch-skip`/`--launch-count` and sections (default SpeedOfLight,
Occupancy, MemoryWorkloadAnalysis, LaunchStats), run under `sudo -n` because
GPU counters need it on 4GPUs. `ncu` exits 0 when nothing matched; the kit
treats "No kernels were profiled" as an error. Percentages are filtered by unit
(`Memory Throughput` exists as both % and Gbyte/s); rejected units are listed.
Durations come from the nsys trace (`--from-trace`); ncu's own duration is
shown for reference only, since it replays kernels with caches flushed.

## What the kit cannot show

- A verdict from fewer than 6 retained pairs, or an effect below the measured
  noise of that series.
- Clean-room numbers on a shared host: it records foreign load and discards
  contaminated rounds, but memory-bandwidth or cache interference from
  processes outside the lane is not observable.
- Exact VRAM peaks: sampling gives lower bounds; the trace high-water excludes
  untraced memory.
- Host-side cost attribution inside a trace or under CPU sampling.
- Per-thread work: `--profile` stages are main-thread only (see
  `docs/stage_profile.md`), and OpenMP sub-stages cover the master's share.
- Scientific equivalence: identity is byte-level against the baseline arm on
  one round, not a numerical tolerance study.
- Multi-GPU or multi-process runs: one payload per run, one GPU.
- `--gpu-metrics-devices` time series: unavailable on 4GPUs even under sudo.

## Acceptance record (4GPUs, 2026-10-09)

MEASURED with kit `0219f71` on GPU0 (A100-80GB PCIe), payload CPUs 96-103,
runner CPUs 120-123, the 24-movie tutorial set and the canonical options of the
example above. Arms: `build-main` (main `9d14275`) and a throwaway
`build-slow` (`usleep(25000)` at the start of "fit polynomial", never
committed). `--pairs 10 --profile-pass 3 --trace-pass 2 --lane-wait 600
--max-rounds 16`. Another user's process (affinity 0-123) migrated on and off
the lane throughout.

| comparison | rounds run / kept / discarded | verdict | median d | 95% CI of median | noise | identity |
|---|---|---|---|---|---|---|
| main vs main | 11 / 10 / 1 (both arms flagged) | not resolved (below noise 0.413 s) | +0.061 s | -0.150..+0.677 s | 0.271 s | PASS, 81 files, 24 MRC |
| main vs slow | 10 / 10 / 0 | resolved slower | +0.580 s (+7.1%) | +0.548..+0.732 s | 0.046 s | PASS, 81 files, 24 MRC |

- Null: no stage flagged in either the `--profile` or the trace deltas.
- Slow: 0.580 s per 24-movie run is 24.2 ms per movie, against the 25 ms that
  was injected. "fit polynomial" is the only stage flagged: +25.18 ms
  `--profile` wall (threshold 0.50 ms, CPU +0.08 ms, so a sleep, not work), and
  +25.31 ms trace wall, all of it device idle. One `--profile` pass of `slow`
  met the lane condition and is named in the report.
- The pair-to-pair scatter on this shared host is about 0.27 s per run
  (≈3%), with occasional ±0.6-1.6 s pairs that the lane monitor does not
  explain. Effects below about 0.4 s per run need more pairs or a quieter
  host.
- Teeth: making `union()` stop merging overlaps fails 8 `ProfilingKit`
  tests; charging idle gaps whole to the segment where they start fails 2;
  discarding only the flagged arm's run fails 2. All were reverted. Checked
  through `ctest -R ProfilingKit` in a build of this branch.

## Relation to older tools

`tools/nsys_analysis/` queries are ported into `lib/nsys_db.py` and
`lib/metrics.py` with fixtures: `stages.py` (per-stage clipping), `gaps2.py`
(idle split), `syncs.py` (blocking calls and device time inside them),
`xfer.py` and `analyze.py` (copies, kernels, API census, VRAM),
`ncu_sum.py` (unit filter) and `folded.py`. `patch_nvtx.py` is superseded by
the NVTX ranges of `--profile`. The chart renderers (`mk*.py`) are not ported.
`tools/single_gpu/` and `tools/profile_cuda_movie.py` remain as campaign
records.
