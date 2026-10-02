# Architecture experiments, 2 October 2026

## Disposition

**Keep multi-movie worker processes. Do not promote a universal FFT batch size
or another synchronization-only production change from this experiment.**
Keep the minimal probes for future resource-policy decisions. Production
numerics and processing behavior were not changed.

The [decision report](DECISIONS.md) connects these results to end-user workflows,
developer experience, other software and the proposed ownership boundaries.

## Source, venue and verification

- Production baseline: `57e98666a6225a8fdb6dafbdbc356478c21cea3a`.
- Tested experiment source: `d14a861`, represented remotely by that baseline
  plus patch SHA256 `96df5a66525a2c3f985edf9f32d591342f9c31df4ee6146c1c1a6e8ec46f33b5`.
  The local/remote hashes of every experiment source and CMake file matched.
  The remote working tree had untracked added tools; its `git diff` hash alone
  is therefore insufficient. See [source-files.sha256](evidence/source-files.sha256)
  and [source-patch.sha256](evidence/source-patch.sha256).
- SCARF `gn3000`, A100-SXM4-40GB, CUDA 12.8, `USE_NVCOMP=OFF`.
  One GPU/four CPUs requested with an exclusive node; Slurm actually reserved
  all **four GPUs and 64 CPUs**. The probes use one logical CUDA device, 0,
  and four build/application threads; inherited CPU affinity was 0–63 (not
  a four-core pin). The opening snapshot had no compute processes. All four
  physical UUIDs are inventoried in `venue.txt`; the logical-to-physical CUDA
  mapping was not independently captured, so no per-UUID performance claim
  is made.
- Job **3521980 completed, exit 0**, elapsed **5m24s**, including build, suite
  and both experiments. Raw outputs remain under
  `/work4/scd/scarf1415/motioncorr/issue142-architecture-20261002`.
- **40/40 CTests passed**, including the eight CUDA-labelled tests (seven
  hardware-labelled), in 102.75 seconds. This establishes that configuration's
  existing suite, not independent scientific acceptance or nvCOMP behavior.
- Local CPU configuration/build remained valid. The job-granularity probe
  passed on macOS. The earlier whole-suite baseline failure of
  `SyntheticRegression` on macOS remains unresolved; no gate was relaxed.

Raw [venue](evidence/venue.txt), [build](evidence/build.log),
[CTest](evidence/ctest.log), [Slurm accounting](evidence/slurm-accounting.txt),
[binary hashes](evidence/binaries.sha256), and
[machine-readable summary](evidence/summary.json) are retained.

## 1. FFT scheduling: speed depends on shape, and so does exactness

The reference invokes `CudaMovieSession::computeGlobalForwardFFT()` and
`computeGlobalInverseFFT()`. A mirror arm reproduces batch-one planning and
per-frame waits; a stage arm queues work in one default stream and waits at
stage boundaries. Batches two/four also change cuFFT plan shape and use a
batch-sized C2R preservation tile. Partial batches have a separate tail plan.

Each geometry has seven rounds with rotated/reversed arm ordering. Each new
plan is warmed once. Input generation and output comparisons are outside
timing; setup is reported separately. The table is the median of forward plus
inverse **stage wall times**, not whole-application time. An output comparison
is inserted between those stages equally in every arm.

| Geometry × frames | Production ms | Stage batch 1 ms | Stage batch 2 ms | Stage batch 4 ms | Batch 4 exact? |
|---|---:|---:|---:|---:|---|
| 256×256×24 | 1.005 | 0.639 | 0.367 | 0.209 | 7/7 |
| 256×256×160 | 5.954 | 3.535 | 1.996 | 1.141 | 7/7 |
| 512×511×25 | 1.491 | 1.125 | 0.796 | 0.582 | 7/7 |
| 1024×768×24 | 1.695 | 1.345 | 1.107 | 0.889 | **0/7** |
| 3710×3838×24 | 46.996 | 46.510 | 46.778 | 46.256 | 7/7 |
| 4096×4096×24 | 20.126 | 19.725 | 18.833 | 18.046 | 7/7 |
| 4096×4096×80 | 67.248 | 66.165 | 62.870 | 60.390 | 7/7 |

All production repeats, mirror controls and stage-batch-one runs were
bit-identical to the reference. Batch two matched on all seven geometries.
Batch four differed only on the tested 1024×768 geometry: inverse maximum
absolute difference **0.000186920**, and **16,205,738 Fourier scalar components**
differed. This is an observed arithmetic change, not evidence of either a
scientific defect or acceptable scientific equivalence.

Across **245 measured observations**, 238 matched exactly and seven reported
that intentional plan-shape difference. Every run retained the Fourier-buffer
checksum across C2R, had finite comparisons and completed successfully. Each
of the seven geometry processes also required a deliberately changed input
to be detected by the comparator. The odd-height/25-frame case exercises tail
plans; the reference is actual production code rather than only a copied loop.

The tutorial-sized batch-four paired saving was **0.739 ms**, 7/7 faster. Its
explicitly owned payload/work/tile memory rose **2716.63 → 3042.71 MiB** versus
the mirror batch-one arm, about **326 MiB** more. These figures omit the
production sum allocation, gain, later stages, CUDA context and library-private
allocations. They are not whole-process peaks. Retained reference buffers are
additional benchmark-only memory.

For 4096×4096×80, batch four saved a paired **6.845 ms**, 7/7 faster, for about
384 MiB more explicitly owned memory. For tiny 256×256×160 it saved 4.814 ms,
also 7/7 faster. The differences are real in these stage measurements; their
fraction of an actual processing job is not established here.

Setup medians span roughly 2–7 ms in an already initialized context. At
512×511×25, tail plans increase candidate setup from about 2.02 ms (batch one)
to 3.38 ms (batch four), exceeding the 0.909 ms paired execution saving if
paid only once for one transform pair. Reusing plans changes that tradeoff.
These setup numbers do not include cold process/CUDA-context startup.

**Decision:** make resource policy an explicit design concern, but keep the
current production choice for now. Do not encode these seven geometries as a
lookup table. A proposed larger-batch policy needs representative movie-level
benefit, numerical/scientific acceptance, admission/cleanup controls and a
whole-worker memory limit. Previous synchronization-only confirmation data
on SCARF did not establish an application gain, and PR #139's graph study is
a separate no-go; neither is overridden by this stage result.

## 2. Job granularity: preserve batching when adding isolation

Six distinct file names containing copies of the same 512×512×8 synthetic TIFF were
processed sequentially, with 1, 2 or 6 movies per invocation. No concurrent
workers, prefetch or new processing implementation were introduced. Use four
compute and four I/O threads, fixed seed, 3×3 patches, dose weighting and both
weighted/unweighted output. Retain one warmup round, then rotate/reverse order
for five measured GPU rounds (three local CPU rounds).

| Movies per invocation | Invocations for six movies | GPU median seconds (range) | Local CPU median seconds (range) |
|---|---:|---:|---:|
| 1 | 6 | 11.246 (11.231–12.452) | 0.546 (0.541–0.570) |
| 2 | 3 | 5.738 (5.734–5.761) | 0.398 (0.381–0.410) |
| 6 | 1 | 2.091 (2.076–2.103) | 0.270 (0.269–0.297) |

The GPU probe observed resident-CUDA execution in every movie's log and
rejected failure/fallback messages. Every arm/round matched all **12 MRCs and
six per-movie STAR files**, comparing complete MRC headers/payloads except the
timestamp and normalizing the per-movie STAR output prefix only. A separate
truncated-MRC control was rejected. Full commands, hashes and observations
are in [GPU observations](evidence/job-granularity-gpu/observations.jsonl) and
[CPU observations](evidence/job-granularity-cpu.jsonl).

The timings include all application work inside each invocation: startup,
processing, output and aggregate/PDF generation. They do not isolate CUDA
context cost. The number of aggregate publications changes between arms, and
those aggregate files were checked for existence but were not merged or
compared across jobs. Local macOS lacks Ghostscript, so its PDF behavior
differs from SCARF; do not compare CPU and GPU columns as a backend speedup.

**Decision:** keep the existing ability to process many movies per invocation
when building process isolation/multi-GPU scheduling. Avoid a launcher that
creates a fresh CUDA process for each movie by default. This is evidence for
preserving batching, not a newly implemented 5.4× acceleration of the current
main program (main already accepts multi-movie input).

This experiment does not test poisoned-device replacement, changing gains,
mixed optics/geometries, long-lived pool growth, multiple GPUs, concurrent
processes on one GPU, network-storage throughput or experimental scientific
diversity. Those are the next discriminating tests for #117/#136/#140.

## Reproduce

```sh
cmake -S . -B build -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 \
  -DUSE_NVCOMP=OFF -DARCHITECTURE_BENCHMARKS=ON -DBUILD_TESTING=ON
cmake --build build --parallel 4
build/movie_fft_bench 1024 768 24 7
python3 tools/architecture/job_granularity.py --binary build/motioncorr \
  --output /new/scratch/directory --gpu
python3 tools/architecture/summarize.py docs/architecture/evidence
```

`run_scarf.sh` records the complete native campaign and checks that it runs in
a Slurm allocation. The benchmark option defaults off and no timing probe is
registered as a correctness CTest. The failed first local job-probe attempt
requested only weighted output while expecting two images; that harness
mistake was corrected by explicitly requesting `--save_noDW` before the
recorded CPU/GPU runs. No native build or native test repair was needed.
