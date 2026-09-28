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

All 24 tutorial movies, one process, one A100, `--j 8`, unprofiled binary `d80cdadb…`:

| | |
| :-- | :-- |
| Process wall | **31.07 s** — `/usr/bin/time` independently reports `0:31.03`, agreeing with the runner's own clock |
| CPU time | 84.4 s, reported by `time` as **271%**, i.e. 2.71 of the 16 allocated CPUs |
| Products | 109, exit 0, equal to baseline on payload, core header and masked labels |
| Backend | **24 of 24 movies carry per-movie CUDA execution evidence; zero fallback warnings** |
| Peak simultaneous process-tree RSS | **1.52 GiB** |
| Device peak, allocator-traced | **3134.34 MiB**, identical on all 24 movies |
| Device peak, NVML-sampled at 0.2 s | **3493 MiB**; the gap is the CUDA context |
| Per-movie device alignment | median **40.6 ms** |
| Context switches | 1745 voluntary, 293 involuntary |
| Filesystem input blocks | 0 — fully page-cache warm |
| Foreign CPU during the run | max 39.2% box-wide, **0 foreign threads inside the lane** |

**One warm-up run did not reach steady state, so this single run is not the best central
estimate.** The first two 24-movie runs of the session were 31.17 s (declared warm-up) and
31.07 s (above), while the same configuration measured later in the session as the
confirmation arm `c_j8_io8` gave a median of **29.16 s over 5 runs**, range 28.44–30.12 s.
The single Phase 0 run therefore sits above the later distribution rather than inside it.
Whatever is still warming beyond the first run — output-path cache, CPU frequency behaviour —
is not identified here. Section 5's `n = 5` figure is the one to quote for this
configuration; this row is retained as the frozen first baseline it was declared to be, not
promoted into a comparison.

The two device figures are different quantities and are labelled as such. The traced figure
is what the allocator recorded; the NVML figure is larger because it includes the CUDA
context. A sampled peak is a lower bound on the true peak at any sampling rate.

**Where the wall time goes.** Two instrumented sources, kept separate.

The `TIMING` build's whole-run breakdown, 24 movies, profiled binary `22e59177…`, wall
29.779 s:

| stage | s | | stage | s |
| :-- | --: | --- | :-- | --: |
| `read movie` | **7.127** | | `detect hot pixels` | 0.859 |
| `apply gain and initial sum` | 4.403 | | `fix defects` | 0.639 |
| `write corrected image` | 2.754 | | `global iFFT` | 0.561 |
| `patch alignment` | 1.654 | | `global FFT` | 0.536 |
| `dose weighting` | 1.370 | | `global alignment` | 0.292 |
| `joint star and logfile pdf` | 1.120 | | `prepare patch` | 0.159 |
| `write star and shift plot` | 0.137 | | `read gain` | 0.129 |
| `fit polynomial` | 0.039 | | `power spectrum`, `binning` | 0.000 |

These nest and overlap and are **not** summed into a total; their naive sum is 21.78 s
against a 29.78 s profiled wall, and that gap is not a residual to attribute. The in-binary
`Timer` is also not thread-safe, so a stage covering parallel work is indicative rather than
exact. These come from the profiled binary and are never mixed into the unprofiled timing
comparison — the unprofiled build emits **zero** `TIMING` stages, which is what makes the two
genuinely separate classes rather than a labelling convention.

**This is the mechanism behind section 4.** Host-side input and output — `read movie`
7.13 s, `apply gain and initial sum` 4.40 s, `write corrected image` 2.75 s — is roughly
14.3 s, while the GPU-accelerated arithmetic — `patch alignment` 1.65 s, `global FFT` +
`global iFFT` 1.10 s, `dose weighting` 1.37 s — is roughly 4.1 s. A pipeline in that shape is governed by
how fast frames can be decoded and written, not by how many threads are available to compute,
which is exactly the behaviour section 4 measures.

The second source is the per-movie CUDA profile block, present in both builds. It reports a
device-side `Total GPU alignment time` with a median of 40.6 ms per movie and a traced peak
allocation of 3134.34 MiB, identical on all 24.

The binary's own per-movie wall timer (`motioncorr_runner.cpp:1261`–`:2557`) sums to 24.53 s
across 24 movies, median 0.970 s, range 0.943–1.692 s. The remaining **6.54 s**, 21% of the
31.07 s run, falls outside that interval and, from the source, comprises process startup, the 24
`plotShifts` EPS writes at `:622`, and `generateLogFilePDFAndWriteStarFiles()` at `:650`,
which shells out to ghostscript three times. The `TIMING` stages above put
`joint star and logfile pdf` at 1.120 s and `write star and shift plot` at 0.137 s, so the
final reporting is a real but minority part of that residual. No TIFF cost anywhere in this
document is derived by subtracting GPU kernel timers from wall time.

**SMT, and why the lane's 16 CPUs may not be 16 cores.** `lscpu` inside this guest reports
`Thread(s) per core: 1`, `Core(s) per socket: 1` and `Socket(s): 124` — a flattened topology
in which every logical CPU is its own socket and its own core. That is a virtualisation
artifact, not the host's real geometry, and it means **the physical-core versus SMT-sibling
distinction the round requires cannot be read from inside this VM at all.** Prior work on
this same host found positive evidence of hidden SMT: a stage running 68% slower at `j=2`
while user time nearly doubled, which is the signature of two threads sharing one physical
core. Every "16 CPUs" in this document therefore means 16 *logical* CPUs on NUMA node 1, and
any statement that would require them to be 16 independent cores is not supported. This is
also a live alternative explanation for part of section 5's small `j16` margin, and it is not
separated here.

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

Median wall of 3 repeats, 4 movies (per-arm observed range in brackets):

| `--j` | IO=1 | IO=2 | IO=4 | IO=8 |
| --: | --: | --: | --: | --: |
| 1 | **11.758** [11.76–12.74] | — | — | — |
| 2 | **11.802** [11.78–12.23] | **8.921** [8.05–8.95] | — | — |
| 4 | **11.819** [11.66–12.32] | **8.595** [8.29–9.20] | **6.998** [6.89–7.34] | — |
| 8 | **12.125** [11.92–12.15] | **8.807** [8.42–8.81] | **7.157** [7.15–7.46] | **6.190** [6.13–6.38] |

Read down a column, not across a row. **At a fixed effective IO-thread count, `--j` has no
measurable effect.** At IO=1 the four medians span 11.758–12.125 s, a 3.1% range, and all
four arms' observed ranges overlap one another; within-arm run-to-run spread is 1.9–10.6%.
The same holds at IO=2 (8.595–8.921, ranges overlapping) and IO=4 (6.998 vs 7.157). If
anything the largest `--j` is marginally the *slowest* at IO=1, which is the opposite of the
direction more compute threads would predict.

Read across and wall time falls monotonically with IO threads: 11.8 → 8.8 → 7.2 → 6.2 s, a
**1.90x speedup from 1 to 8**. CPU-seconds rise only from 11.7 to 14.3 across that range, so
this is parallel speedup in the input stage rather than work being displaced.

**On the CUDA path `--j` matters only because, left uncapped, it also sets the IO thread
count.** That is orthogonal to all six bottlenecks this issue proposes — FFTW plan locks,
dose-weighting cache traffic, transcendental stalls, Amdahl residue, OpenMP barriers and NUMA
latency — each of which concerns `--j`-parallel host compute, and none of which can govern a
curve that does not respond to `--j`. This does not refute those mechanisms on the CPU
backend, which section 6 measures separately.

**Controls.** All 12 arms produced products identical to the reference for their own input
set — MRC payload, MRC core header, and MRC labels with only RELION's clock stamp masked,
which is the decomposition `docs/gate_contract.md` publishes as `--gate exact`. STAR, EPS and
per-movie log content were compared after substituting the run's own absolute output path,
which MotionCorr embeds in the EPS plot title, `corrected_micrographs.star` and the `.pdf.lst`
lists. PDFs gate the verdict on **presence only**. No run exited non-zero. No arm lost a movie.

**Ghostscript PDF output is nondeterministic in length here, which corroborates the
project's separately tracked PDF differences.** Presence is enforced, size is not, and the
reason is measured rather than assumed: the *same* arm re-run produced `logfile.pdf` of
104632 and 104634 bytes with every other product bit-identical, and across `--j` on the CPU
backend the sizes scatter without order — 104640, 104640, 104640, 104777, 104639, 104640 for
j = 1, 2, 4, 8, 16, 32. The 137-byte outlier at j=8 is scatter, not a `j` dependence, and
gating on size would have failed two arms for a property of the PDF writer. A lost PDF is
still a lost product and still fails the arm.

**Cross-pass determinism.** The instrument correction in section 10 forced a complete
re-measurement, which yields a control that was not planned: the same 13 arms, same binary
`d80cdadb…`, same inputs, run as two independent passes hours apart, produced
**bit-identical MRC payloads in 13 of 13 arms**. So the CUDA backend is deterministic
run-to-run at this configuration, and the timing arms are comparing genuinely identical
computations rather than merely similar ones.

This is a **same-backend** statement only. It says nothing about CUDA-versus-CPU agreement,
where `docs/reference_gates.md` records Gate 2 failures on all 24 movies; that is a different
requirement and it is not addressed here.

**Positional bias.** Every slot in this schedule was occupied by more than one arm, which is
what makes the slot statistic informative at all — had each arm kept a fixed slot, every
ratio would be that arm's wall over its own median, ≈1.0 by construction, and the section
would read as "no bias" regardless of the truth. The report now checks and states this. The
pooled slot ratios show no monotone trend. The two-arm contrasts in section 5 give a direct
estimate instead, via `observed = E ± P`.

**Interference.** Foreign CPU peaked at 131.9% during one arm and 0–7.1% elsewhere, with
**zero** foreign threads observed inside the `96-111` lane in any run. The 131.9% arm
(`p1_j2_io2`) is not an outlier in wall time, which is consistent with foreign work outside
the lane barely touching a tasksetted run.

## 5. Phase 1 confirmation — finalists on all 24 movies

The screen's optimum sat at the edge of the screened range and the lane holds 16 logical
CPUs, so `j16` was tested rather than assumed; without it the study would have recommended
the largest value it happened to try.

| arm | n | median | range | spread | CPU-s |
| :-- | --: | --: | :-- | --: | --: |
| `--j 16`, no IO cap | 8 | **27.773 s** | 27.49–28.08 | 2.1% | 87.5 |
| `--j 8`, no IO cap | 5 | 29.163 s | 28.44–30.12 | 5.8% | 77.5 |
| `--j 16 --max_io_threads 8` | 3 | 29.757 s | 29.38–29.90 | 1.8% | 77.1 |

All three arms produced products equal to the baseline; no run exited non-zero.

Paired, order alternating within every pair, `d` positive means the named arm was slower:

| contrast | n pairs | per-pair `d` (s) | mean ± 2 sem | sign | effect `E` | positional `P` |
| :-- | --: | :-- | :-- | :-- | --: | --: |
| `j8/io8` − `j16/io16` | 5 | 1.11, 2.13, 0.72, 1.69, 1.29 | **+1.387 ± 0.486** | 5/5 | **+1.474** | −0.436 |
| `j16/io8` − `j16/io16` | 3 | 2.08, 2.27, 1.29 | **+1.880 ± 0.597** | 3/3 | **+1.977** | +0.290 |

Neither interval spans zero and every pair agrees in sign. The sign test itself cannot carry
these: at n=5 and n=3 it cannot reach even the 5% level, which is a property of the design
rather than of the data, and the report says so rather than quoting a p-value the n cannot
support. The paired differences and their spread are the evidence.

**What actually moves the time is the IO threads, again.** Holding `--j 16` and lifting the
IO cap from 8 to 16 is worth **1.98 s** (`E`, second row). Holding the IO cap at 8 and
raising `--j` from 8 to 16 goes the *other* way — 29.757 s against 29.163 s, about 0.6 s
slower. That last comparison is **unpaired**: no pair in this schedule contained both arms,
so it is indicative only and weaker than the two rows above. It does not contradict them,
and it matches the screen.

The positional term `P` is −0.436 s and +0.290 s in the two contrasts — same order as the
effect in the second case. Recovering it was free from the alternation, and it is a concrete
reason not to run an A/B in fixed order here.

**Interference.** Foreign CPU peaked at 56.9–80.4% box-wide across the three arms with
**zero** foreign threads inside the `96-111` lane in any run, measured with the repaired
sampler of section 10.

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

Hold the aggregate CPU budget fixed at the 16-logical-CPU lane and compare, with each
worker's **entire process tree** pinned inside a disjoint sub-range of `96-111`:

| layout | per-worker lane | `--j` | aggregate effective IO threads |
| :-- | :-- | --: | --: |
| 1 worker | `96-111` | 8 | 8 |
| 1 worker | `96-111` | 16 | 16 |
| 2 workers | `96-103`, `104-111` | 4 | 8 |
| 2 workers | `96-103`, `104-111` | 8 | 16 |
| 4 workers | `96-99`, `100-103`, `104-107`, `108-111` | 2 | 8 |
| 4 workers | `96-99`, `100-103`, `104-107`, `108-111` | 4 | 16 |

These are hypotheses, not measured optima. The layout deliberately crosses worker count with
aggregate IO threads, because section 4 predicts that **aggregate IO threads, not worker
count, is what moves throughput** — and a 1/2/4-worker series run only at fixed per-worker
`--j` confounds the two. Rows sharing an aggregate IO count are the informative comparison:
if they land together, the worker count is not the variable.

Each worker needs its own GPU or an explicit statement that they share one; sharing is a
different experiment from the scaled-resource series below. Device memory budgeting starts
from the measured 3134 MiB traced peak per process at this geometry, which is what bounds how
many workers fit, not the device's 80 GiB.

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

1. **Set `--j` to the lane width and leave `--max_io_threads` unset.** On the 16-CPU lane
   that is `--j 16`, measured at 27.77 s against 29.16 s for `--j 8`, 5/5 paired. The value
   of raising `--j` is that, uncapped, it raises the IO thread count with it — at a *fixed*
   IO cap of 8, going from `--j 8` to `--j 16` was slightly slower, not faster.
2. **Do not set `--max_io_threads` below `--j` on the GPU path.** It is the one setting
   measured here that clearly costs throughput: IO=1 is 1.93x slower than IO=8 at the same
   `--j`.
3. **Budget ~3.2 GiB of device memory and ~1.6 GiB of host RSS per process** at this movie
   geometry. The traced allocator peak was 3134 MiB on every one of the 24 movies, and the
   NVML-sampled peak 3493 MiB including context. This, not the device's 80 GiB, is what
   bounds how many workers fit.
4. **One process leaves the lane mostly idle** — 2.71 of 16 cores at `--j 8`. That headroom
   is an argument for more concurrent movies, which is #53's lane, not for more threads per
   movie.
5. **Expect ~29 s per 24 movies warm, and do not trust a single warm-up run.** The first two
   24-movie runs of a session came in ~2 s above the steady-state distribution that the same
   configuration reached later.

Explicitly **not** established: any best `--j` for the CPU backend on current main (section 6
pending); any multi-worker or multi-GPU recommendation (section 7 unrun); behaviour at other
frame counts, geometries, formats or heterogeneous movie costs (Phase 3, out of scope); and
anything about cold-cache or networked storage, since every number here is warm-cache local
disk.

## 9. PR22 and PR57, inspected and not imported

Both were inspected read-only at their current heads. Neither is imported: they modify
`src/`, which is outside this issue's whitelist, and the round prohibits pulling stale
production code in to retain evidence.

**PR22 `bdfc374` — instrumentation.** It makes `Timer` thread-safe by giving each OpenMP
thread its own `ThreadTimerData` (`src/time.h`) instead of sharing one `start_times` vector.
That is exactly the defect behind this report's caveat that a stage covering parallel work is
indicative rather than exact, so **if PR22 lands, the section 3 stage table becomes exact
rather than indicative** and is worth re-measuring. Its parser
(`tools/benchmark_cpu_profile.py:99`) uses `[A-Za-z0-9_\s\-()]` with the hyphen escaped, so
the historical bug that silently dropped every hyphenated tag (`dw - iFFT`,
`prep patch - FFT`) is indeed fixed at this head. Its pattern requires the
`sec (N microsec/operation)` form, which independently matches the strict rule arrived at
here; `envelope_runner.py` additionally parses the CUDA `ms` profile block, which PR22's does
not, so the two are complementary rather than duplicates.

**PR57 `13845fb` — the dead global inverse FFT.** Fourteen production lines adding
`need_real_space_before_dw = do_local || !do_dose_weighting || save_noDW` and skipping the
transform when it is false. **It does not fire in anything measured here:** every arm in this
report uses `--patch_x 5 --patch_y 5`, so `do_local` is true and the guard always takes the
original path. PR57 is therefore orthogonal to every number above, and none of these results
should be read as evidence for or against it.

On #66's note that even/odd must be counted as a real-frame consumer: the one write of
real-space `Iframes` between the global inverse transform and the post-dose-weighting
transform that this inspection located is `motioncorr_runner.cpp:1805`, which sits inside
`#ifdef WRITE_FRAMES` with its `#define` commented out at `:1800`, so it is disabled debug
output rather than a live consumer. That is an observation from a bounded read, **not** a
correctness audit of PR57; its guard condition remains its owner's to verify.

## 10. Instrument corrections, and what they changed

The first pass of this study was measured with an instrument that had four witnesses which
could not observe what they asserted. An independent read-only review found them; each was
checked against retained artifacts or a purpose-built control before being accepted, and the
GPU series was then **re-run** on the repaired instrument rather than published with caveats.
They are recorded here because a measurement study that hides its own instrument failures is
not worth more than the failures.

| Witness | Defect | Consequence | Resolution |
| :-- | :-- | :-- | :-- |
| `TIMING` stage intervals | parsed only the per-movie logs, but the profiled build writes its breakdown to **stdout** | the profiled arm recorded nothing the unprofiled arm did not; separately, prose such as `Frames to be used: 1 2 3 …` was stored as a 1.0-second stage that does not exist | both formats now matched strictly and kept in separate namespaces; a control asserts prose is rejected and `dw - iFFT` survives. **This is how the section 3 breakdown was obtained at all.** |
| CUDA execution | a startup banner printed in `initialise()` before any movie is read | a run in which all 24 movies fell back to the CPU would have been indistinguishable from a GPU run, while looking several times slower for no recorded reason | per-movie evidence plus fallback-warning capture. Re-checked on the retained first-pass run: **24/24 movies carry CUDA execution evidence, zero fallback warnings**, so the first-pass numbers were not affected |
| Interference | `ps pcpu` is cputime ÷ lifetime, and ownership came from a walked `ps` snapshot | a lifetime average sampled at 1 Hz is not a time series; and the walk raced with the sampler's own children, recording `foreign_cpu_max = 2750%` against its own `ps` and MotionCorr's own `gs` | `/proc` `utime+stime` deltas, threads in state `R` only, ownership by session id. Same host, same lane, after: **39.2% box-wide max, 0 threads inside the lane** |
| Process wall | the `/usr/bin/time` line is `Elapsed (wall clock) time (h:mm:ss or m:ss): 0:31.03`, split on the first colon | the field was never captured on any run | split on the last colon; now recorded alongside the runner's own measurement as a cross-check |

Of these, only the interference figures from the first pass were actually wrong. The product
equality, the wall times and the stage structure all survived re-measurement, and the
conclusions in sections 4 and 5 are unchanged.

The `cpu64` series in section 6 was allowed to finish on the earlier instrument rather than
restarted. Its conclusion is a paired unbound-versus-bound contrast inside one lane, where
self-contamination is present identically in both arms of every pair and cancels in the
difference. Its interference figures are labelled instrument v1 and are an upper bound.

## 11. Reproducing

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

```bash
python3 tools/test_envelope_interference.py --lane 96-111   # Linux only; skips elsewhere
```

`-DCMAKE_CUDA_ARCHITECTURES=80` is required. `CMakeLists.txt:59` guards its own fallback with
`if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)`, but `enable_language(CUDA)` has already defined
the variable, so the fallback never fires and a configure without the flag dies with
`CUDA_ARCHITECTURES is empty for target "motioncorr_core"`. Every caller in the repo passes it
explicitly, which is why the dead fallback has stayed invisible.
