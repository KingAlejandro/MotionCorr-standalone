# MotionCorr operating envelope on current main

Measured for [#26](https://github.com/KingAlejandro/MotionCorr-standalone/issues/26) against
main `4c952b3f54479653512c4d208e09c9a8c02f3726`, under the contract in
[`agents/designs/issue_26_operating_envelope.md`](../agents/designs/issue_26_operating_envelope.md).
Raw per-run records: [`benchmark_logs/issue26_envelope_2026-09-27/`](benchmark_logs/issue26_envelope_2026-09-27/).

This measures **execution speed and resource use**. It is not a numerical-accuracy result, a
known-truth result, or a scientific-equivalence result; those are different requirements and
passing this one certifies none of them. What it does establish is that every timed arm
produced products identical to the frozen baseline, so the timings compare like with like.

## 1. Why none of the existing numbers could be reused

Three bodies of timing evidence exist for this issue and all three describe something other
than current main. The issue body's table predates the shared-host CPU cap and assumed all
124 logical CPUs. The 2026-09-25 audit in this issue's first comment is careful work but
pins source `3e3a1967`, which predates #82, #90 and #91 — merged TIFF, gain-cache and
damaged-movie changes that land directly on the stages it timed. PR55's four-GPU SCARF
figures lost their timed output arrays. A historical timing is not relabelled current after a
rebase, so all three are prior art re-checked here, not a baseline extended.

## 2. Provenance

| | |
| :-- | :-- |
| Source | `4c952b3f…`; archive `6d5de834…`; 650 files; tree digest `787a3061…` |
| CUDA Release | `d80cdadb…` — `CXX -O3 -DNDEBUG -std=gnu++17 -fopenmp`, `CUDA -O3 -DNDEBUG -std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80]` |
| CUDA Release + `TIMING` | `22e59177…` — identical flags plus `-DTIMING`; a separate class, never mixed into a timed comparison |
| Toolchain | gcc 13.3.0, nvcc 12.8.61, driver 570.86.10, FFTW 3.3.10, libtiff 6.0.1, CMake 3.28.3 |
| Host | `4-gpu-vm`, AMD EPYC 7452, 124 logical CPUs, 2 NUMA nodes (0–61, 62–123), 432 GiB |
| Device | CUDA ordinal 0, `CUDA_VISIBLE_DEVICES` unset. NVML index 0 is `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, A100 80 GB PCIe. The two namespaces are distinct in general, so the identification is evidenced rather than assumed: the NVML sampler on index 0 tracked the run from idle to 3429 MiB, which no other device did |
| CPU lane | `taskset -c 96-111`; inherited `Cpus_allowed_list` verified `96-111` on every run; all 16 on NUMA node 1 |
| 24-movie STAR | `fb998f70…` — matches this issue's own reference STAR |
| gain / movie 00021 | `8919cdc7…` / `df298b1b…` — match `docs/reference_gates.md` |
| Screening subset | `ed74c9ed…` (00021, 00029, 00042, 00049); byte-identical STAR on both hosts |
| Options | `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1` |

`CMAKE_BUILD_TYPE=Release` is read back from `CMakeCache.txt` and the literal `flags.make`,
not assumed: the repo sets no default, so an unqualified configure produces `-O0` and would
inflate every host-side stage.

**Cache regime.** Host page cache held 403 GiB against 3.19 GB of movie input, and
`/usr/bin/time` reports `File system inputs: 0` for every run. These are warm-cache numbers.
Dropping caches is forbidden on a shared host, so the regime is recorded rather than
controlled. Zero reported filesystem input blocks does not make decode free — it only means
the bytes did not come from the device.

## 3. Phase 0 — frozen Release one-GPU baseline

All 24 tutorial movies, one process, one A100, `--j 8`:

| | |
| :-- | :-- |
| Process wall | **29.03 s** (1.21 s/movie) |
| CPU time | 39.52 s user + 37.69 s sys = 77.2 s, i.e. **2.66 cores** of the 16 allocated |
| Products | 109, exit 0, bit-equal to baseline |
| Peak simultaneous process-tree RSS | **1.52 GiB** (89 samples at 0.25 s) |
| Device peak, allocator-traced | **3134.34 MiB**, identical on all 24 movies |
| Device peak, NVML-sampled at 0.2 s | **3429 MiB**; mean utilisation 23.5%, max 57% |
| Context switches | 1775 voluntary, 215 involuntary |
| Foreign CPU during the run | 0.0% mean, 0.0% max; 0 foreign threads inside the lane |

The two device figures are different quantities and are labelled as such. The traced figure
is what the allocator recorded; the NVML figure is larger because it includes the CUDA
context. A sampled peak is a lower bound on the true peak at any sampling rate.

**Where the wall time goes.** Two instrumented sources, kept separate.

The `TIMING` build's whole-run breakdown, 24 movies, profiled binary `22e59177…`:

| stage | s | | stage | s |
| :-- | --: | --- | :-- | --: |
| `read movie` | **7.082** | | `detect hot pixels` | 0.843 |
| `apply gain and initial sum` | 3.789 | | `fix defects` | 0.596 |
| `write corrected image` | 2.954 | | `global iFFT` | 0.560 |
| `patch alignment` | 1.589 | | `global FFT` | 0.537 |
| `dose weighting` | 1.361 | | `global alignment` | 0.263 |
| `joint star and logfile pdf` | 1.101 | | `prepare patch` | 0.149 |
| `write star and shift plot` | 0.129 | | `read gain` | 0.100 |
| `fit polynomial` | 0.037 | | `power spectrum`, `binning` | 0.000 |

These nest and overlap and are **not** summed into a total; their naive sum is 21.09 s
against a 28.64 s profiled wall, and that gap is not a residual to attribute. The in-binary
`Timer` is also not thread-safe, so a stage covering parallel work is indicative rather than
exact. These come from the profiled binary and are never mixed into the unprofiled timing
comparison — the unprofiled build emits **zero** `TIMING` stages, which is what makes the two
genuinely separate classes rather than a labelling convention.

**This is the mechanism behind section 4.** Host-side input and output — `read movie` 7.08 s,
`apply gain and initial sum` 3.79 s, `write corrected image` 2.95 s — is roughly 13.8 s,
while the GPU-accelerated arithmetic — `patch alignment` 1.59 s, `global FFT` + `global iFFT`
1.10 s, `dose weighting` 1.36 s — is roughly 4.0 s. A pipeline in that shape is governed by
how fast frames can be decoded and written, not by how many threads are available to compute,
which is exactly the behaviour section 4 measures.

The second source is the per-movie CUDA profile block, present in both builds. It reports a
device-side `Total GPU alignment time` with a median of 40.2 ms per movie and a traced peak
allocation of 3134.34 MiB, identical on all 24.

The binary's own per-movie wall timer (`motioncorr_runner.cpp:1261`–`:2557`) sums to 22.93 s
across 24 movies, median 0.934 s, range 0.914–1.333 s. The remaining **6.09 s** of the 29.03 s
run falls outside that interval and, from the source, comprises process startup, the 24
`plotShifts` EPS writes at `:622`, and `generateLogFilePDFAndWriteStarFiles()` at `:650`,
which shells out to ghostscript three times. The `TIMING` stages above put
`joint star and logfile pdf` at 1.101 s and `write star and shift plot` at 0.129 s, so the
final reporting is a real but minority part of that residual. No TIFF cost anywhere in this
document is derived by subtracting GPU kernel timers from wall time.

**NUMA placement.** The lane pins CPUs to node 1 but `Mems_allowed_list` stays `0-1` — memory
is not bound. `numastat -p` sampled mid-run nonetheless shows **1.43 GB of 1.45 GB resident on
node 1**, 98.6% node-local, and `numa_maps` shows `N1=` for heap and anonymous mappings. So
first-touch placement achieves locality here without an explicit memory policy. This is a
point-in-time sample taken early in the run, not a peak, and it is a statement about this
lane, not a general claim.

## 4. Phase 1 — thread and I/O screen

Ten distinct **effective** treatments, three repeats each, on the declared 4-movie subset.
`--max_io_threads` above `--j` is clamped to `--j` at `motioncorr_runner.cpp:1280`, so the
nominal 4x4 grid contains ten treatments, not sixteen; timing the six duplicates would have
reported the same configuration under different names. Every run's effective settings were
read back from the binary's own per-movie log and checked against the request.

Median wall of 3 repeats, 4 movies:

| `--j` | IO=1 | IO=2 | IO=4 | IO=8 |
| --: | --: | --: | --: | --: |
| 1 | **12.214** | — | — | — |
| 2 | **12.112** | **9.495** | — | — |
| 4 | **12.164** | **8.941** | **7.230** | — |
| 8 | **12.116** | **9.499** | **7.434** | **6.322** |

Read down a column rather than across a row. **At a fixed effective IO-thread count, `--j` has
no measurable effect.** The spread across four values of `--j` at IO=1 is 12.112–12.214 s, or
0.8%, against a run-to-run spread of 2.5–8.4% within single arms. The same holds at IO=2
(8.94–9.50) and IO=4 (7.23–7.43).

Read across instead and wall time falls monotonically with IO threads: 12.2 → 9.5 → 7.3 →
6.3 s, a 1.93x speedup from 1 to 8. CPU-seconds rise only from 12.1 to 14.3 over the same
range, so this is genuine parallel speedup in the input stage, not work being moved.

**On the CUDA path `--j` matters only because, left uncapped, it also sets the IO thread
count.** That is orthogonal to all six bottlenecks this issue proposes — FFTW plan locks,
dose-weighting cache traffic, transcendental stalls, Amdahl residue, OpenMP barriers and NUMA
latency — every one of which concerns `--j`-parallel host compute. None of them can be the
explanation for a curve that does not respond to `--j`. This does not refute those mechanisms
on the CPU backend, which section 6 measures separately; it says they do not govern the GPU
configuration.

**Controls.** All 12 arms produced products identical to the reference for their own input
set — MRC payload, MRC core header, and MRC labels with only RELION's clock stamp masked,
which is the decomposition `docs/gate_contract.md` publishes as `--gate exact`. STAR, EPS and
per-movie log content were compared after substituting the run's own absolute output path,
which MotionCorr embeds in the EPS plot title, `corrected_micrographs.star` and the `.pdf.lst`
lists. PDFs were checked for presence and size only, since ghostscript stamps a creation
date. No run exited non-zero. No arm lost a movie.

**Positional bias.** Pooled over arms, the mean ratio of wall time to that arm's median by
slot within a repeat ranges 0.986–1.033 with no monotone trend, so the design's order
rotation did not leave a systematic first-slot or last-slot advantage in this series. The
rotation is kept regardless: the bias is a property of the workload, not of the host, and has
been measured at 20 ms for a TIFF/MRC change on this machine.

**Interference.** Foreign CPU peaked at 131.9% during one arm and 0–7.1% elsewhere, with
**zero** foreign threads observed inside the `96-111` lane in any run. The 131.9% arm
(`p1_j2_io2`) is not an outlier in wall time, which is consistent with foreign work outside
the lane barely touching a tasksetted run.

## 5. Phase 1 confirmation — finalists on all 24 movies

*Executing. Five pairs of `j8/io8` against `j16/io16` and three of `j16/io16` against
`j16/io8`, order alternating within every pair, all 24 movies.* The screen's optimum sits at
the edge of the screened range and the lane holds 16 logical CPUs, so j=16 is tested rather
than assumed — otherwise the study would recommend the largest value it happened to try.

## 6. CPU backend scaling on cpu64

*Executing. `--j` in {1, 2, 4, 8, 16, 32} crossed with unbound versus
`OMP_PROC_BIND=spread OMP_PLACES=cores`, three repeats, 4-movie subset, lane `taskset -c 0-31`
= NUMA node 0.*

Two `ctffind` processes run permanently on that host at ~100% each and are **unpinned**
(`Cpus_allowed_list: 0-63`), so they enter the measurement lane; one was observed on CPU 18
mid-series. They are not altered and not waited out. The lane settle gate is expected to time
out at the start of this series, and that timeout is the evidence that a clean lane is not
obtainable on this host rather than a defect in the gate.

## 7. Phase 2 — fixed-budget worker protocol, prepared and not executed

#53/PR55 owns executable workers; this task does not write a competing scheduler. The
protocol is specified here so it can be run against that implementation without redesign.

Hold the aggregate CPU budget fixed at the 16-logical-CPU lane and compare one worker at
`--j 8`, two at `--j 4`, four at `--j 2`, each worker's **entire process tree** pinned inside a
disjoint sub-range of `96-111`, with explicit IO caps. These are hypotheses, not measured
optima. Given section 4, the first quantity to record is each layout's aggregate effective IO
thread count, since that — not the worker count — is what the single-process data predicts
will move the throughput.

Thread binding must not be applied blindly to a multi-process layout. The prior audit measured
`spread`+`cores` turning an 84.2 s four-process arm into 255.0 s, a 3x pessimisation, because
each process binds independently against the same place list and all four land on the same
cores. For several processes the correct form is disjoint `taskset` sets with `OMP_PROC_BIND`
left unset.

A scaled-resource series, where host CPU count grows with GPU count, is a **separate** series
and is never merged into the fixed-budget curve. VM 80 GB and SCARF 40 GB device results are
never joined into one speedup curve either.

## 8. Operating guide

Supported by the data in sections 3 and 4, for **this** configuration — one A100, 24 tutorial
movies at 3710x3838x24, 5x5 patches with dose weighting, warm page cache, 16-CPU lane:

1. **Set `--j` for the IO threads you want, and do not expect compute threads to help.** Wall
   time tracks the effective IO-thread count and is flat in `--j` at fixed IO. The uncapped
   default is the right choice because it makes IO threads equal `--j`.
2. **Do not set `--max_io_threads` below `--j` on the GPU path.** It is the one setting
   measured here that clearly costs throughput: IO=1 is 1.93x slower than IO=8 at the same
   `--j`.
3. **Budget ~3.2 GiB of device memory and ~1.6 GiB of host RSS per process** at this movie
   geometry. The traced allocator peak was 3134 MiB on every one of the 24 movies.
4. **One process at `--j 8` leaves the lane mostly idle** — 2.66 of 16 cores. That headroom is
   an argument for more concurrent movies, which is #53's lane, not for more threads per movie.

Explicitly **not** established: any best `--j` for the CPU backend on current main (section 6
pending); any multi-worker or multi-GPU recommendation (section 7 unrun); behaviour at other
frame counts, geometries, formats or heterogeneous movie costs (Phase 3, out of scope); and
anything about cold-cache or networked storage, since every number here is warm-cache local
disk.

## 9. Reproducing

```bash
cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DTIMING=OFF -DBUILD_TESTING=OFF
cmake --build build-cuda -j 8
taskset -c 96-111 flock -w 7200 /tmp/motioncorr-bench.lock \
  python3 tools/envelope_runner.py --plan plan_p0p1.json --out results/p0p1 --own-user "$USER"
python3 tools/envelope_report.py --series results/p0p1/series.json \
  --results-dir results/p0p1 --reference-arm p0_base_24_j8 --reference-arm p1_j8_io8
python3 tools/test_envelope_report.py      # controls for the equality verdict itself
```

`-DCMAKE_CUDA_ARCHITECTURES=80` is required. `CMakeLists.txt:59` guards its own fallback with
`if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)`, but `enable_language(CUDA)` has already defined
the variable, so the fallback never fires and a configure without the flag dies with
`CUDA_ARCHITECTURES is empty for target "motioncorr_core"`. Every caller in the repo passes it
explicitly, which is why the dead fallback has stayed invisible.
