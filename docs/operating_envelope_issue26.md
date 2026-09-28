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
| Device memory, per-call size accounting | largest single reported value **1569.59 MiB** (global call); 25 patch calls report 62.59 MiB each. **Not a peak and not an allocator trace** — see below |
| Device memory, NVML sampled at 0.2 s | **3493 MiB** whole-device, a distinct sampled observation. Not a capacity bound and not reconcilable with the accounting figure |
| Per-movie device alignment | median **40.6 ms** |
| Context switches | 1745 voluntary, 293 involuntary |
| Filesystem input blocks | 0 — fully page-cache warm |
| Foreign CPU during the run | max 39.2% box-wide, **0 foreign threads inside the lane** — repaired instrument: `/proc` interval deltas, state `R` only, session-id ownership. Not comparable to §6.3's v1 figure |

**One warm-up run did not reach steady state, so this single run is not the best central
estimate.** The first two 24-movie runs of the session were 31.17 s (declared warm-up) and
31.07 s (above), while the same configuration measured later in the session as the
confirmation arm `c_j8_io8` gave a median of **29.16 s over 5 runs**, range 28.44–30.12 s.
The single Phase 0 run therefore sits above the later distribution rather than inside it.
Whatever is still warming beyond the first run — output-path cache, CPU frequency behaviour —
is not identified here. Section 5's `n = 5` figure is the one to quote for this
configuration; this row is retained as the frozen first baseline it was declared to be, not
promoted into a comparison.

**Correction: there is no allocator-traced peak in this study.** An earlier revision reported
"3134.34 MiB, allocator-traced, identical on all 24 movies" and explained the gap to the NVML
figure as the CUDA context. Both statements are withdrawn.

`Peak GPU memory allocated` is printed once per global or local CUDA call. In a 5x5 movie
that is 26 lines: 25 patch calls at 62.59 MiB and one global call at 1569.59 MiB. The runner
summed repeated keys, so 25 x 62.59 + 1569.59 = **3134.34** — an artifact of the parser, not a
measurement. Worse, the number landed close to the real 3493 MiB NVML sample, which is
exactly why the invented "gap is the CUDA context" story looked plausible.

The underlying value is also not a trace. At the measured source,
`cuda_alignpatch.cu:310-318` builds `total_vram_allocated` by adding buffer-size expressions
plus the cuFFT workspace for **one function call**; `cuda_realspace_dw.cu` does the same
independently for the reconstruction path. It is function-level size accounting. No statistic
taken from it — sum, max or median — is a process high-water mark.

The parser now refuses to publish a sum for size-like tags and keeps every occurrence
separately (`tools/test_envelope_runner.py` pins that two sequential 100 MiB stages must not
become a 200 MiB peak). What can honestly be said: the largest single accounting value is
1569.59 MiB, the NVML whole-device sample peaked at 3493 MiB, and **these are not the same
quantity and neither is a capacity bound.** Establishing a real per-process high-water mark
needs live allocation accounting or an actual allocator trace, which this study did not do.

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
device-side `Total GPU alignment time` with a median of 40.6 ms per movie. Its memory lines
are per-call size accounting and are handled in the correction above, not treated as a peak.
Its kernel-stage timings are also kept separate from end-to-end wall throughout: in
particular the gain/sum wrapper includes H2D transfer and is not pure host computation.

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

**NUMA placement — withdrawn for this dataset.** An earlier revision reported "1.43 GB of
1.45 GB resident on node 1, 98.6% node-local" for the payload. That is withdrawn in full.

The runner spawned `taskset -c <mask> /usr/bin/time -v motioncorr` and sampled `proc.pid`,
which is the launcher: `taskset` execs into `/usr/bin/time`, not into MotionCorr. The
retained `numa_maps` proves it — every mapping in the captured head reads
`file=/usr/bin/time`. And `numastat -p` reports **MB**, so its "Total 1.45" was 1.45 **MB** of
launcher memory, read as 1.45 GB of movie arrays. The witness described the wrong process in
the wrong units, and the 98.6% figure characterises `/usr/bin/time`.

So this study establishes **no** payload NUMA residency, and no node-locality or first-touch
claim survives. Two neighbouring witnesses are unaffected and stand:

- **cpuset inheritance** — `Cpus_allowed_list: 96-111`, `Mems_allowed_list: 0-1`, read from
  the launcher. `taskset` sets the mask before exec and it is inherited across exec and fork,
  so it does apply to the payload. It is now additionally read from the resolved payload pid.
- **Process-tree RSS** — 1.52 GiB peak, sampled over the launcher and its children, which
  does include MotionCorr. This is a residency total, not a per-node breakdown.

The runner now resolves the live payload through `/proc/<pid>/exe`, records its pid, session
and start time, and aggregates per-node residency from `numa_maps` page counts times each
mapping's own `kernelpagesize_kB` — bytes, with the unit stated. `tools/test_envelope_runner.py`
pins it with a tiny launcher in front of a child holding a known 256 MiB allocation: the
witness must identify the child and report its residency, not the parent's. Re-measuring
payload NUMA is listed as an unrun case; it needs a GPU slot this task no longer holds.

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

Read across **at fixed `--j 8`**, the only row where all four IO settings were measured:
12.125 → 8.807 → 7.157 → 6.190 s, a **1.959x** speedup from IO=1 to IO=8. An earlier revision
quoted 1.90x, which compared `j1/io1` against `j8/io8` and therefore changed both variables
at once; that figure is corrected. CPU-seconds rise only from 12.1 to 14.3 across the fixed-j
row, so this is parallel speedup in the input stage rather than work being displaced.

**What is supported: no material `--j` effect was detected at fixed effective IO in this
screen.** The stronger reading — that `--j` matters *only* through IO — is **not** supported
and is withdrawn: this is one movie geometry, one backend, one patch configuration, warm
cache, `--j` ≤ 8 in the screen, and a null within this noise is not a universal law. Nor does
it refute the six bottlenecks the issue proposes on the CPU backend; it says they do not
govern *this* configuration, and section 6 measures that backend separately.

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

| contrast | n | per-pair `d` (s) | mean | descriptive 95% t CI | sign | `E` | `P` |
| :-- | --: | :-- | --: | :-- | :-- | --: | --: |
| `j8/io8` − `j16/io16` | 5 | 1.11, 2.13, 0.72, 1.69, 1.29 | +1.387 | **[+0.712, +2.062]** | 5/5 | +1.474 | −0.436 |
| `j16/io8` − `j16/io16` | 3 | 2.08, 2.27, 1.29 | +1.880 | **[+0.596, +3.165]** | 3/3 | +1.977 | +0.290 |

**Correction to an earlier revision.** It quoted `mean ± 2 sem` and then treated exclusion of
zero as a significance decision. At these sample sizes that is not a 95% interval: the
two-sided *t* factor is 2.776 at n=5 and **4.303** at n=3, not 2. The intervals above are
descriptive 95% *t* intervals recomputed from the exact paired JSON. Both still exclude zero,
so the direction of this result is unchanged — but they are **not order-adjusted, not
multiplicity-adjusted**, and they rest on a small-sample normal-difference assumption. They
are a description of the spread, not a significance test.

The sign counts are likewise descriptive: a **two-sided** sign test needs n ≥ 6 to reach even
the 5% level, so at n=5 and n=3 no sign result here can be significant. That is fixed by the
design before any data exists.

**What moves the time in this experiment is the IO threads.** Holding `--j 16` and lifting
the IO cap from 8 to 16 is worth **1.98 s** (`E`, second row). Holding the IO cap at 8 and
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

CPU-only Release build `CUDA=OFF`, 4-movie subset, lane `taskset -c 0-31` (= NUMA node 0),
`--j` crossed with thread binding, three repeats, arms paired with order alternating.
Medians of 3; **read this section with section 6.3 in hand, the lane was not clean.**

### 6.1 The phenomenon this issue reports reproduces on current main

| `--j` | unbound | speedup | par. eff | `spread`+`cores` | speedup | par. eff | binding effect |
| --: | --: | --: | --: | --: | --: | --: | --: |
| 1 | 180.25 s | 1.00x | 100.0% | 187.82 s | 1.00x | 100.0% | +4.2% |
| 2 | 94.38 s | 1.91x | 95.5% | 105.05 s | 1.79x | 89.4% | +11.3% |
| 4 | **78.56 s** | **2.29x** | **57.4%** | 63.76 s | 2.95x | 73.6% | **−18.8%** |
| 8 | 41.76 s | 4.32x | 54.0% | 27.99 s | 6.71x | 83.9% | **−33.0%** |
| 16 | 29.02 s | 6.21x | 38.8% | 20.89 s | 8.99x | 56.2% | **−28.0%** |
| 32 | 19.52 s | 9.24x | 28.9% | 18.91 s | 9.93x | 31.0% | −3.1% |

Unbound parallel efficiency at `j=4` is **57.4%**, against the **55.8–56.0%** this issue
reports on the 4-gpu-vm and the **57.1%** the 2026-09-25 audit measured on this host at
source `3e3a1967`. So the phenomenon is real, it is not an artifact of the old hardware or
of the old source, and **#82/#90/#91 did not remove it**. These are medians of 3 on a
contaminated lane (§6.3); the agreement across three independent studies is what carries the
claim, not the precision of this table.

### 6.2 Thread placement, paired

| `--j` | mean `d` (unbound − bound) | descriptive 95% t CI | pairs bound faster | `E` | `P` |
| --: | --: | :-- | :-- | --: | --: |
| 1 | −21.57 s | [−84.15, +41.01] | 0/3 | −17.22 | −13.05 |
| 2 | +9.60 s | [−81.71, +100.90] | 2/3 | +19.73 | −30.39 |
| 4 | +17.89 s | [−5.85, +41.64] | 3/3 | +20.65 | −8.26 |
| 8 | **+11.69 s** | **[+0.63, +22.75]** | 3/3 | +12.45 | −2.27 |
| 16 | **+7.43 s** | **[+2.76, +12.10]** | 3/3 | +6.91 | +1.54 |
| 32 | +2.50 s | [−5.51, +10.51] | 3/3 | +2.04 | +1.38 |

**Correction to an earlier revision, which used `± 2 sem` and claimed `j=4` as resolved.**
Under a descriptive 95% *t* interval (factor 4.303 at n=3, not 2), `j=4` **spans zero** and is
**not** resolved. `OMP_PROC_BIND=spread OMP_PLACES=cores` is resolved as faster only at
**`j` = 8 and `j` = 16**; at `j` = 1, 2, 4 and 32 the interval spans zero. All six point
estimates at `j` ≥ 4 favour binding and 3/3 pairs agree in sign at each, which is suggestive,
but suggestive is what it is.

Even that survives only as **provisional**, because §6.3 shows the lane was contaminated —
these intervals do not include that contamination. The direction still matches the
2026-09-25 audit (−29.7% at j=4, −28.8% at j=8, −26.1% at j=16) on current main, which is the
independent support the point estimates lean on. Recommendations from this section stay
provisional pending a re-measurement on a controlled lane.

Note `P` at `j=2` is −30.4 s against an effect of +19.7 s: the positional term is *larger
than the effect*. An unpaired, fixed-order A/B at that point would have reported the wrong
sign with confidence. This is the concrete case the alternation exists for.

### 6.3 The lane was not exclusive, and the CPU numbers are correspondingly weaker

The interference record shows foreign work inside the 0-31 lane, but it supports a narrower
statement than a first reading suggests. Three quantities in the artifact must not be
conflated:

- **`foreign_threads_inside_mask.max = 63`** (arm `c1_j2_spread`, 70 samples) is the
  **aggregate over all commands at the single worst sample**. It is not any one command's
  count.
- **`foreign_in_mask_by_command`** for that arm — `python` 1321, `ctffind` 114, `ps` 27,
  `sshd` 1 — is **accumulated thread-sample hits across the whole arm**, not simultaneous
  threads. Dividing by the sample count would give an average, not a maximum.
- **No per-sample series was retained, and no PID, session id or command line was recorded
  for foreign processes.** So per-command simultaneity is **not recoverable** from this
  record, and ownership **cannot be attributed**.

What the artifact does support: at the worst of 70 samples in `c1_j2_spread`, **63 foreign
threads in total** had a last-run CPU inside 0-31; and across that arm the dominant in-mask
command label was an **unidentified Python workload**, ahead of `ctffind`. That workload is
deliberately **not attributed to any task, worker or checkout**, because nothing was retained
that could attribute it. The `ps` entries are this run's own sampler (see below). `ctffind`
is the known permanent unpinned pair, untouched.

**The GPU and CPU in-mask figures are different measurements and are not a like-for-like
contrast.** The CPU arms ran on **instrument v1**, whose own recorded definition is *"any
thread outside this run's own process subtree using >1% CPU"* — that is, `psr`, the last-run
CPU, for any thread regardless of run state, gated on a **lifetime-average** `pcpu`. It
therefore counts sleeping threads, cannot resolve activity during the run, and its ownership
test is a process-tree walk that races with the sampler's own children, which is why `ps`
appears in its own foreign list. The GPU arms ran on the **repaired instrument**: CPU
actually consumed between consecutive samples from `/proc` `utime+stime` deltas, threads in
state `R` only, ownership by session id. A `0` from the second and a `63` from the first are
not the same quantity and must not be subtracted or ranked against each other.

What *is* comparable, because it does not involve the sampler at all, is the **wall-time
spread**: `j2_unbound` spans 92.1–155.2 s (67%) and `j1_spread` 181.1–230.7 s (26%) on
cpu64, against 1.8–5.8% on the GPU confirmation arms. That contrast stands on the timing
data alone.

**So sections 6.1 and 6.2 are weaker evidence than sections 4 and 5 and are not
interchangeable with them.** The direction of both is supported — 6.1 independently by two
prior studies, 6.2 by 3/3 sign agreement at three consecutive `j` values — but the
magnitudes carry contamination whose size this record cannot bound. A load-bearing CPU
recommendation needs a re-measurement on a lane that is actually exclusive, with per-sample
and PID-level interference retained.

One further limit: this is a 4-movie subset on one host, not a dataset-scale CPU throughput
result.

All 12 arms produced products equal to the reference on payload, core header and masked
labels; no run exited non-zero.

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
different experiment from the scaled-resource series below. Device-memory budgeting for concurrent workers **cannot** be derived from this study: it has
no per-process high-water mark, only per-call size accounting and a whole-device NVML sample.
Obtain a real allocator trace before sizing worker counts against device capacity.

Thread binding must not be applied blindly to a multi-process layout. The prior audit measured
`spread`+`cores` turning an 84.2 s four-process arm into 255.0 s, a 3x pessimisation, because
each process binds independently against the same place list and all four land on the same
cores. For several processes the correct form is disjoint `taskset` sets with `OMP_PROC_BIND`
left unset.

A scaled-resource series, where host CPU count grows with GPU count, is a **separate** series
and is never merged into the fixed-budget curve. VM 80 GB and SCARF 40 GB device results are
never joined into one speedup curve either.

## 8. Operating guide

Supported by the data in sections 3, 4 and 5, for **this** configuration — one A100, 24 tutorial
movies at 3710x3838x24, 5x5 patches with dose weighting, warm page cache, 16-CPU lane:

1. **Set `--j` to the lane width and leave `--max_io_threads` unset.** On the 16-CPU lane
   that is `--j 16`, measured at 27.77 s against 29.16 s for `--j 8`, 5/5 paired. The value
   of raising `--j` is that, uncapped, it raises the IO thread count with it — at a *fixed*
   IO cap of 8, going from `--j 8` to `--j 16` was slightly slower, not faster.
2. **Do not set `--max_io_threads` below `--j` on the GPU path.** It is the one setting
   measured here that clearly costs throughput: at fixed `--j 8`, IO=1 is **1.959x** slower
   than IO=8.
3. **Host RSS is ~1.52 GiB per process** at this movie geometry (peak of simultaneously
   sampled process-tree totals). **No device-memory budget is recommended here.** The earlier
   "~3.2 GiB traced peak, so that is what bounds worker count" guidance was built on a parser
   artifact and is withdrawn; the per-call accounting maximum (1569.59 MiB) and the NVML
   whole-device sample (3493 MiB) are different quantities and neither is a per-process
   high-water mark. Sizing concurrent workers needs a real allocator trace first.
4. **One process leaves the lane mostly idle** — 2.71 of 16 cores at `--j 8`. That headroom
   is an argument for more concurrent movies, which is #53's lane, not for more threads per
   movie.
5. **Expect ~29 s per 24 movies warm, and do not trust a single warm-up run.** The first two
   24-movie runs of a session came in ~2 s above the steady-state distribution that the same
   configuration reached later.

Explicitly **not** established: any per-process device-memory high-water mark, and therefore
any device-capacity worker-sizing rule (§3 correction); any payload NUMA residency or
node-locality claim (§3 correction); a load-bearing best `--j` for the CPU backend, because
the `cpu64` lane was not exclusive during section 6; any multi-worker or multi-GPU recommendation (section 7 unrun); behaviour at other
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

### Which series ran on which instrument

| series | instrument | interference metric in force |
| :-- | :-- | :-- |
| GPU Phase 0, screen, confirmation (§3–§5) | **repaired** | `/proc` `utime+stime` deltas between samples; threads in state `R` only; ownership by session id |
| cpu64 scaling (§6) | **v1** | `ps` `pcpu`, a **lifetime average**; any thread by `psr` regardless of run state; ownership by a process-tree walk that races with the sampler's own children |

Every record self-documents which applied, in its `sampling.foreign_definition` field.

The `cpu64` series was allowed to finish on v1 rather than restarted, because its conclusion
is a paired unbound-versus-bound contrast inside one lane, where self-contamination is
present identically in both arms of every pair and largely cancels in the difference. Three
consequences follow and are applied throughout §6:

1. Its foreign-CPU totals include the sampler's own `ps` and MotionCorr's own `gs`, so they
   are an **upper bound**, not a measurement.
2. Its in-mask thread counts include **sleeping** threads and are gated on a lifetime
   average, so they cannot resolve activity during the run.
3. Its figures are therefore **not comparable** to the GPU figures and are never contrasted
   with them numerically. Where §6 compares lane cleanliness across hosts it uses wall-time
   spread, which does not involve the sampler.

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
