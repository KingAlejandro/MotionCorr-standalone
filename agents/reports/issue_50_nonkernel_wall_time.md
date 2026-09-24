# Non-kernel wall time on PR #51 (24 September 2026)

## Scope

Investigation of the host-side (non-kernel) wall time of MotionCorr for the matched
Issue #50 / PR #51 case, plus one narrowly scoped improvement in output code.

Explicitly **not** touched: GPU arithmetic, defect logic, `src/acc/cuda/cuda_movie_session.*`,
and acceptance tolerances. Nothing was pushed and PR #51 was not altered.

## Provenance

| Item | Value |
|---|---|
| Base commit | `a11f2f15d8a3f6a8c93f43ca0458e7ff63e08267` (origin/feat/issue-50-cuda-end-to-end-residency) |
| Branch | `t3code/optimize-non-kernel-wall-time` (worktree `t3code-7749899d`, not pushed) |
| Tracer commit | `6ef59e7` — instrumentation only, compiled out by default |
| Improvement commit | `22c31bb` — `src/rwMRC.h` only |
| Host | `4GPUs` / `4-gpu-vm`, 4x NVIDIA A100 80GB PCIe, 124 cores, 432 GB RAM |
| CUDA / driver | CUDA 12.8 (`/usr/local/cuda/bin/nvcc`) |
| Ghostscript | 10.02.1 |
| GPU used | 0 |

### Command under test

```
motioncorr --i /tmp/issue47-clean-source-bench-20260924/benchmark_input.star \
  --o <outdir> --use_own --j 8 --group_frames 3 --patch_x 5 --patch_y 5 \
  --bfactor 150 --gainref .../Movies/gain.mrc --angpix 1.06 \
  --dose_weighting --dose_per_frame 1.277 --gpu 0 --seed 1
```

Movie `20170629_00021_frameImage.tiff`, 3710 x 3838 x 24 frames. Normal MRC, STAR, EPS
and PDF output enabled.

### Input hashes (SHA-256)

```
afc1445e0cd7004f2c3aef81d1538d10ba245bf6c51b33932234a500bf2e6131  benchmark_input.star
df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0  20170629_00021_frameImage.tiff
8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1  gain.mrc
```

### Binary hashes (SHA-256) and build flags

| Arm | Source | `CXX_FLAGS` | SHA-256 |
|---|---|---|---|
| base | `a11f2f1` | `-std=gnu++17 -fopenmp` | `8fe8fd62aa5c4f78a16a85b667580f6a7cde1258ccd512a0bbcd636d8b8587c2` |
| candidate | `22c31bb` | `-std=gnu++17 -fopenmp` | `5677c266e285ee6ea2c2ce5f3cdf35edf2b80763d74684af7ec59f7403dce0a0` |
| base -O2 | `a11f2f1` | `-O2 -ffp-contract=off -std=gnu++17 -fopenmp` | `859dbf6cf5377bb435a1b987d05162636b816591fa638a258b85518011cdda7c` |
| candidate -O2 | `22c31bb` | `-O2 -ffp-contract=off -std=gnu++17 -fopenmp` | `0381243f808a0bfdcb197b4af7e800beea0926da9c89873bdd7e1f3cf7b8ba5b` |

All four: `CUDA=ON TIMING=ON`, `CMAKE_CUDA_ARCHITECTURES=80`,
`CUDA_FLAGS = -std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80]`.

**The first two carry no optimization flag.** `CMakeLists.txt` sets no default
`CMAKE_BUILD_TYPE`, so an unqualified configure yields `-O0` for every host translation
unit while nvcc still gets its own default for device code. This matches how the committed
PR #51 evidence was produced, and is the reason the `-O2` arms exist.

## Method

### Instrumentation

`src/stage_trace.h` (commit `6ef59e7`) adds host stage boundaries the existing `TIMING`
stage timers do not cover: process entry, the first CUDA API call, the destructor window
*after* the per-movie timer stops, the MRC write internals, and each ghostscript
subprocess. A mark is one `clock_gettime(CLOCK_MONOTONIC)` plus two stores into a
preallocated array; nothing is written until an `atexit` dump. It is behind a new
`STAGE_TRACE` CMake option and expands to `((void)0)` when off, so the measured
production binaries are unaffected by its presence.

The tracer is not thread safe by design (unsynchronised function-local statics); marks
must not be placed inside an OpenMP region. None of the current sites are.

### Measurement discipline

Timed runs on this host must be exclusive **box-wide, not per-GPU** — host CPU, page
cache and PCIe are shared. Five sessions were working on the same box, so:

- the whole series runs under `flock /tmp/motioncorr-bench.lock`, queued and fired
  unattended rather than polling for a quiet moment (point-in-time probing races with
  whoever is about to start);
- **all builds run inside the lock**, which is safe because the lock already guarantees
  nobody else is measuring, and which closes the race where a build lands between
  acquiring the lock and the first measured run;
- after building, the window waits for compilers to clear and load1 to fall below 1.5
  before measuring, and logs how long it waited so a stalled wait is visible;
- base and candidate runs are **interleaved** with a discard warm-up per arm, so drift
  during the series hits both arms equally and a paired comparison is available.

### A discarded first series

An earlier series is **not** reported. Its quiescence guard never fired: `pgrep -f`
matches full command lines, so the guard matched its own command-line string — with zero
compilers running it reported four matches, all guard strings. The series ran while load
fell from 14.7 to 7.3. Only its drift-independent results (peak RSS, output hashes) were
retained, and they agree with the clean series below. Quiescence probes must use
`pgrep -x` on process names.

### Comparison method

MotionCorr output is **not byte-reproducible between runs of the same binary**, for
reasons unrelated to numerics:

- `src/rwMRC.h` writes a `"Relion    <date>  <time>"` label into the MRC header at
  offsets 224-1023 via `strftime`;
- Ghostscript's `pdfwrite` embeds `/CreationDate` and a time-derived `/ID` in every PDF.

Both were confirmed by running the **unmodified baseline** twice and diffing. `.eps`
files are byte-reproducible; per-movie `.log` files differ only in timing values.

Comparisons therefore hash MRC **pixels (bytes 1024+)** and **header bytes 0-223 plus
1024** separately — a split that still gates `amin`/`amax`/`amean` at offsets 76/80/84
and `arms` at 216. The whole label field is excluded, not a narrower observed range: a
window fitted to one sample passes today and fails at a date boundary.

The output directory path is embedded in STAR and EPS files, so both arms are run at the
**same** output path and the results moved aside between runs; otherwise every file
differs spuriously.

## Parity of the change

The improvement (`22c31bb`) touches `src/rwMRC.h` and nothing else.

### Byte-level, A100 / Linux / GCC / CUDA, same output path

```
sizes equal: True 56956944
total differing bytes: 2
offsets: [251, 252]
all within MRC label block 224..1023: True
pixel payload (>=1024) identical: True
header 0..223 identical: True
```

Because header bytes 0-223 are byte-identical, the four statistics this change
recomputes — `amin`, `amax`, `amean`, `arms` — are **bit-identical**, not merely equal at
printed precision. An independent session sampling 12 runs saw differing header bytes
spanning 249-252; same field, wider sampling of the timestamp.

Also byte-identical: per-movie STAR (the trajectories), joint `corrected_micrographs.star`,
and every `.eps`. PDFs differ, as they do between two runs of the unmodified baseline.

### Second toolchain: macOS / AppleClang / arm64, `CUDA=OFF`, CPU-only

Both arms rebuilt from source on an unrelated compiler, architecture and code path, run at
the same output path on the CPU-only synthetic fixture across five output modes —
dose-weighted, no dose, `--save_noDW`, `--bin_factor 2`, and `--j 4`. Every corrected MRC
(pixels and header bytes 0-223), every STAR and every EPS byte-identical. The only
differences anywhere were `.log` files, containing `Full movie wall time: 0.307` vs
`0.301` and a progress-bar second count.

`--float16` and `--grouping_for_ps` could not run on the small synthetic fixture — both
binaries fail identically, one on a CLI constraint (`--float16` requires power spectra)
and one on fixture size (`cropInFourierSpace`). Those two modes are covered against the
real movie separately.

The repo's own `SyntheticRegression` test fails **identically** on both arms
(image max diff `2.364986e+01`, RMSE `3.119288e-01`, shift RMSD `3.305323e-03`). That is a
pre-existing `a11f2f1` failure on this toolchain, not a regression; the bit-for-bit
agreement of those four metrics is itself a parity data point.

### Review

An independent reviewing session found a real defect in the first version of the write
predicate: it listed `SChar`, which `writeMRC` **can** emit but `castPage2Datatype` has no
case for — it falls to `default:` and reports an error. Accepting it would have converted a
loud failure into a silent raw write. Verified and fixed; the predicate is now restricted to
the three cases that `writeMRC` can emit *and* `castPage2Datatype` implements as a memcpy
(`Float`/`float`, `SShort`/`short`, `UShort`/`unsigned short`), with the exclusions
documented so they are not casually widened. `Double` and `UChar` were also dropped as
unreachable from `writeMRC`.

The `typeid` test is load-bearing rather than redundant with the size test: `Image<int>`
maps to `output_type == Float` with a matching size and must keep taking the converting path.

## Where the host time goes

Lock-held stage trace, medians of three runs per arm, baseline arm built from `a11f2f1`
with the tracer only. Host wall intervals; they do not synchronise CUDA, so an interval
may overlap asynchronous device work.

| Interval | base | inside per-movie timer? |
|---|---:|---|
| argument parsing | 0.000 s | no |
| `cudaGetDeviceCount` — **first CUDA call, runtime/driver init** | **0.292 s** | no |
| rest of `initialise()` | 0.001 s | no |
| movie setup + gain read + CUDA session | 0.109 s | yes |
| **TIFF read, 24 frames** | **0.734 s** | yes |
| GPU pipeline (gain/sum, defects, FFT, align, dose weighting) | 1.119 s | yes |
| **MRC write** | **0.264 s** | yes |
| post-timer destructors (~1.4 GiB host + CUDA session) | 0.208 s | no |
| per-movie STAR write | 0.002 s | no |
| per-movie EPS plot | 0.003 s | no |
| joint STAR table build + write | 0.001 s | no |
| summary EPS write | 0.008 s | no |
| **ghostscript, 4 spawns** | **0.419 s** | no |
| exit | 0.003 s | no |

Traced span 3.179 s; the portion outside the per-movie work is 0.834 s.

(The 0.734 s here and the 0.730 s in the thread sweep below are the same stage measured
with different binaries — the traced baseline build and the thread-sweep experiment build.
The 4 ms is build-to-build, not drift.)

Three things this settles:

1. **Ghostscript is spawned four times, not once** — `header.pdf`, `batch.pdf`,
   `all_batches.pdf`, `logfile.pdf` (`motioncorr_runner.cpp:1100, 1115, 1121, 1124`).
   Bare `gs` startup on this host is ~60 ms, so most of the 0.419 s is process startup
   rather than work. `all_batches.pdf` is a single-input re-encode of `batch.pdf`.
2. **CUDA runtime initialisation is 0.292 s and sits outside the per-movie timer**, at
   `motioncorr_runner.cpp:252`. It is not reducible by any I/O or output change. cuFFT
   plan construction is separately measured at 5.5 ms + 2.1 ms, so it is not this.
3. **STAR and EPS generation are negligible** (0.014 s combined). The untimed output block
   is the MRC write and ghostscript, not metadata.

## The MRC write

| Sub-interval | base | candidate |
|---|---:|---:|
| header statistics (`computeMin`/`Max`/`Avg`/`Stddev`) | 0.164 s | 0.054 s |
| staging `calloc` + `memcpy` + free | 0.046 s | 0.000 s |
| `fwrite` | 0.054 s | 0.062 s |
| **total** | **0.264 s** | **0.117 s** |

Four passes over 14,238,980 pixels to fill four header fields. The `fwrite` is slightly
slower afterwards because it now streams from the live array rather than from a scratch
buffer that was just written and is therefore warm in cache — a real cost, and still a
large net win.

## Measured effect

Interleaved base/candidate pairs, discard warm-up per arm, exclusive box-wide lock,
quiescence gate satisfied (waited 110 s, load 1.46, zero compilers).

### Unoptimized build — matches how PR #51 evidence was produced

**n = 15 pairs** (settled: waited 40 s, load 1.46, zero compilers):

| Metric | base median | candidate median | paired mean | paired median | sign-flip p |
|---|---:|---:|---:|---:|---|
| process wall | 3.360 s (sd 0.079) | 3.150 s (sd 0.063) | −0.221 s | −0.220 s | **0.0001 — RESOLVED** |
| per-movie timer | 2.218 s | 2.005 s | −0.222 s | −0.217 s | **0.0001 — RESOLVED** |
| peak host RSS | 1,633,912 KiB | 1,586,340 KiB | −47,438 KiB | **−47,288 KiB** | **0.0001 — RESOLVED** |

14 of 15 pairs are negative for wall time.

**Order-reversed replication.** The series above runs base then candidate in every pair,
which confounds the arm with its position: if running second is systematically faster
(warm page cache, ramped GPU clocks) the bias is credited to the candidate. The whole
series was therefore repeated with the within-pair order flipped:

| Ordering | paired mean | paired median | negative pairs | p |
|---|---:|---:|---:|---|
| base first (candidate runs 2nd) | −0.2213 s | −0.220 s | 14/15 | 0.0001 |
| candidate first (base runs 2nd) | −0.1820 s | −0.190 s | **15/15** | 0.0001 |
| pooled | **−0.2017 s** | −0.210 s | 29/30 | — |

The effect survives the reversal, so it is not positional. Better, running both orderings
separates the two terms. With `observed = −E − P` when the candidate runs second and
`observed = −E + P` when it runs first:

- **true candidate advantage E = 0.202 s**, i.e. **−6.0% of a 3.356 s baseline**
- **positional bias P = 20 ms** in favour of whichever arm runs second

So the headline is **−0.202 s (−6.0%)**, and the single-ordering figure of −0.220 s was
about 20 ms optimistic.

Two notes on method, both from comparing this with a sibling task that used
alternating-within-pair ordering over 40 pairs:

- **Alternation is not merely a cancellation.** If the ordering label is kept per pair and
  the series split afterwards, alternation recovers `P` from the same data at no extra
  cost, with each direction at half n. A separate reversed series gives cleaner separation
  and full n per direction. Either beats a single fixed order; there is no real trade-off
  between them, only a choice of where the n goes.
- **`P` is workload-specific and should not be assumed negligible.** On this same host the
  sibling task measured `P = 2.5 ms` for a GPU-side arithmetic change, against 20 ms here.
  That is consistent with the mechanism: this change is dominated by TIFF read and MRC
  write, where page-cache carryover between consecutive runs is exactly what `P` captures.
  At 20 ms, `P` would have been a material fraction of a 46 ms effect.

An earlier n = 6 series on the same binaries did **not** resolve the wall gain
(paired median −0.175 s, p = 0.19) because two candidate runs were outliers. It resolved
the RSS reduction at p = 0.031, the floor for a two-sided sign-flip test at n = 6. Both
series are reported; n = 6 was simply underpowered for an effect of this size against this
spread, which is worth recording because n = 3 is the convention in the existing evidence.

The wall delta (−0.221 s) and the per-movie-timer delta (−0.222 s) agree to 1 ms, which is
the expected signature: the change lives entirely inside the per-movie timer.

It also exceeds the −0.147 s measured directly at the MRC write in the traced runs. Part of
the remainder is visible (destructors 0.208 → 0.195 s, consistent with ~47 MB less to
release); roughly 0.055 s is **not** accounted for by any single traced interval.

Page-fault counts narrow this but do not close it. From `/usr/bin/time -v`, the candidate
takes **18,345 fewer minor page faults** than the baseline (median, uncapped). The removed
staging buffer is 54.3 MiB = 13,901 pages, so **4,444 faults are avoided beyond the buffer
itself** — real, and consistent with less downstream allocator pressure. But the buffer's own
faults are incurred *inside* the traced 46 ms alloc/cast/free interval and are therefore
already counted; only the beyond-buffer faults are candidates for the residual, and at a
plausible 1–3 µs per fault those are worth **4–13 ms, not 55 ms**.

So the mechanism is real but too small, and the gap stays open. The traced and unprofiled
binaries also differ, which limits how hard the two numbers can be compared. I am not going
to invent a mechanism for the rest.

**Why this change does show a memory saving when a superficially similar one does not.**
`askMemory` is `calloc` (`src/memory.cpp:30`), and 54.3 MiB is far above any mmap threshold,
so the allocation itself hands back lazily-faulted zero pages — it is the `memcpy` that
touches them. Removing the buffer removes both the allocation and the write, so the faults
genuinely never happen, which is why RSS drops by ~47 MB and faults by ~18.3k. A sibling
task removing a *write* to a buffer that `initZeros()` has already faulted in
(`motioncorr_runner.cpp:1311`) correctly measured no fault saving and −408 KiB of RSS.
Same apparent shape, different mechanism: what matters is whether the pages are ever
touched, not how many bytes stop being written.

### `-O2 -ffp-contract=off`

| Metric | base median | candidate median | paired median | sign-flip p |
|---|---:|---:|---:|---|
| process wall | 2.585 s | 2.570 s | −0.015 s | 0.53 — **not resolved** |
| per-movie timer | 1.429 s | 1.412 s | −0.021 s | 0.53 — **not resolved** |
| peak host RSS | 1,633,810 KiB | 1,585,544 KiB | **−48,320 KiB** | **0.031 — resolved** |

`p = 0.031` is the smallest value a two-sided sign-flip test can return at n = 6; it is
reached only when every pair has the same sign, which the RSS deltas do and the wall
deltas do not.

### The build type is a larger lever than the change

Same source, same host, same lock, only `CXX_FLAGS` differing:

| Arm | unoptimized | `-O2 -ffp-contract=off` | difference |
|---|---:|---:|---:|
| base | 3.390 s | 2.585 s | **−0.805 s (−24%)** |
| candidate | 3.245 s | 2.570 s | −0.675 s (−21%) |

Contraction is pinned off deliberately: GCC defaults to `-ffp-contract=fast`, and FMA
fusion changes float results, so plain `-O3` is not a parity-preserving change.

**With contraction off, the optimized build is bit-identical to the unoptimized one.**
Comparing an unoptimized run against an `-O2 -ffp-contract=off` run of the same arm:

```
base-01   header[0:224] 23648ea59f4a76fb...   pixels 09680a6a4b3914f9...
          -O2 identical: header True   pixels True   per-movie STAR identical
cand-01   same, identical
```

One movie and one comparison per arm on the GPU host. It was then **independently
confirmed on a second machine and CPU-only toolchain** (`cpu64` / small-refmac-machine,
64-core, GCC 13.3, `CUDA=OFF`), building both arms in both configurations and running the
repo's synthetic fixture through all four:

```
arm/cfg   hdr[0:224]         pixels             per-movie STAR
base_o0   44794b65e49e7999   04c2a1d9349b3c09   6254fd456f07154b
base_o2   44794b65e49e7999   04c2a1d9349b3c09   6254fd456f07154b
cand_o0   44794b65e49e7999   04c2a1d9349b3c09   6254fd456f07154b
cand_o2   44794b65e49e7999   04c2a1d9349b3c09   6254fd456f07154b
```

One distinct hash in every column. All five cross-comparisons (including the
`base -O0` vs `cand -O2` diagonal) show zero non-`.log` mismatches. So the 0.805 s is
available without a numerical tradeoff on two toolchains, provided contraction stays off.

## The largest single I/O cost: TIFF read

The movie read is **already 8-way parallel** over the 24 frames
(`motioncorr_runner.cpp:1266`, `num_threads(n_io_threads)`, and `n_io_threads == n_threads`
because `max_io_threads` defaults to -1). The 0.734 s is therefore 8-thread wall time, not
single-thread. Its cost is entropy decode, not I/O: the file is page-cache warm on repeat
runs, and libtiff mmaps it.

Thread-count sweep, same binary, only the read-loop thread count varying, run in rotated
rep-major order so thread count cannot be confounded with drift. Four reps each:

| threads | `ceil(24/t)` rounds | `read movie` median | spread |
|---:|---:|---:|---|
| **8** (what `--j 8` gives today) | 3 | **0.730 s** | 0.727–0.732 |
| 12 | 2 | 0.499 s | 0.494–0.513 |
| 16 | 2 | 0.506 s | 0.494–0.518 |
| **24** | 1 | **0.291 s** | 0.285–0.293 |

The cost is a **discrete round count**, not a smooth scaling curve: 12 and 16 threads are
indistinguishable because both need two rounds over 24 frames, while 24 threads needs one.
No continuous-scaling artifact produces that signature, which is what makes this a
measurement rather than an extrapolation.

**~0.439 s is available and it is bit-exact** — one corrected-pixel hash across all 16
sweep runs. The loop body has no cross-iteration state and no floating-point accumulation;
each iteration opens its own `TIFF*` and writes its own frame.

**It is not shipped here.** `n_io_threads` is derived from `n_threads`, so taking it
requires decoupling decode parallelism from `--j`, which changes what that flag means for
every user and raises transient memory (one strip buffer per thread). That is a maintainer
policy decision, not an I/O cleanup.

**And it does not survive an 8-CPU cap.** Repeating the endpoints inside the
`taskset -c 96-103` pool the GPU host now runs under:

| threads | `read movie`, 124 CPUs available | `read movie`, capped to 8 CPUs |
|---:|---:|---:|
| 8 | 0.730 s | 0.754 s |
| 24 | **0.291 s** | **0.751 s** |

The entire 0.439 s disappears, which is what the round-count model predicts: 24 decode
threads on 8 cores still take three rounds, they are just time-sliced instead of queued.
Corrected pixels identical throughout. So this recommendation is worth ~0.44 s on an
unconstrained host and **nothing** on a core-constrained one — it is a function of the
deployment, not of the code, and should be evaluated against whatever core budget the
production pipeline actually gets. Raising `--j` itself is **not** an option: `n_threads`
drives floating-point reductions elsewhere (e.g. the hot-pixel `reduction(+:mean)`), so
changing it can change the hot-pixel set and therefore the output.

## Output-mode coverage on the real movie

Both arms run at the same output path on movie `00021`, GPU 0, under the lock:

| Mode | Result |
|---|---|
| dose weighted (the matched case) | MRC, STAR, EPS identical |
| no dose weighting | identical |
| `--save_noDW` (two MRC writes) | identical |
| `--float16 --grouping_for_ps 4` | identical — output MRC **mode 12**, plus a mode-2 `_PS.mrc` |
| `--grouping_for_ps 4` (extra MRC) | identical |
| no gain reference | identical |
| `--gain_rot 1` | both arms fail identically: gain reference dimensions do not match a rotated non-square image |
| `--bin_factor 2` | both arms fail identically: binned dimensions must be even |

In every mode that runs, the **only** differing file is the per-movie `.log`, and every one
of its differing lines is a timing value.

`--float16` matters most here: it drives `output_type == Float16`, which
`castPage2Datatype` implements as a real conversion and which the new direct-write
predicate deliberately excludes. It still produced a byte-identical mode-12 MRC, confirming
the converting path is untouched.

## Verdict

**The wall gain is resolved.** **−0.202 s, −6.0%**, from 30 paired runs across both arm
orderings (29/30 pairs negative; p = 0.0001 in each ordering separately), on the
unoptimized build that the PR #51 evidence was produced with. The RSS reduction of
about −47,500 KiB is resolved in every series run, including at `-O2`.

Three qualifications, all material:

1. **At `-O2` the wall gain is not resolvable** (paired median −0.015 s, p = 0.53). The
   four statistics passes are slow largely *because* the build is unoptimized; once they
   vectorise, removing three of them saves little. The RSS reduction survives at `-O2`
   (−48,320 KiB, p = 0.031), because it is an allocation that no longer happens rather than
   work that got faster.
2. **The build type is a bigger lever than this change.** Configuring
   `-O2 -ffp-contract=off` is worth −0.805 s (−24%) on the same source and host — more than
   three times the change. If the Issue #50 target is process wall time, that is the first
   thing to fix, and it is a configure flag rather than a patch.
3. **The largest single I/O cost, the ~0.73 s TIFF read, is untouched.** ~0.439 s of it is
   available bit-exactly, but only by decoupling decode threads from `--j`, and only on a
   host with spare cores — measured worth nothing under the 8-CPU cap.

So: a real, reproducible, bit-exact improvement that removes genuinely redundant work and
one whole-image allocation — but not the largest lever available, and its wall-time
component is partly an artifact of an unoptimized build. It should be taken on the merits of
the work it removes, not as the answer to Issue #50's timing target.

## Recommendations, in descending value

1. **Set a default `CMAKE_BUILD_TYPE`** (and record the configure line in benchmark
   evidence). Worth ~0.8 s here, and measured bit-identical on this movie with
   `-ffp-contract=off` pinned. That pin is not optional: without it GCC fuses `a*b+c` into
   an FMA and float results change. Confirm across the 24-movie set before flipping the
   default.
2. **Decouple the movie-read thread count from `--j`.** ~0.439 s, bit-exact, but a
   user-visible policy change: more threads than `--j` requests, and one strip buffer per
   thread. Needs maintainer sign-off, and must *not* be done by raising `n_threads`, which
   feeds floating-point reductions that determine the hot-pixel set. **Conditional on
   cores being available**: measured worth nothing under an 8-CPU cap, so decide it against
   the production core budget rather than against this host.
3. **Reduce the ghostscript chain.** 0.419 s across four spawns, most of it process
   startup. `header.pdf` and `batch.pdf` are independent and could be produced
   concurrently; `all_batches.pdf` is a single-input re-encode of `batch.pdf`. Not done
   here because the equivalence argument rests on PDFs that are already non-deterministic,
   and the repo has no page-content gate to back it — that gate should be built first.
4. **Cache the gain reference across movies.** `Igain` is local to
   `executeOwnMotionCorrection`, so a 24-movie run re-reads the same ~57 MB MRC 24 times,
   about 2.5 s. Not visible in this single-movie case. Must be a cache keyed on
   *(filename, nx, ny, EER-or-not)* falling through to a fresh read on mismatch, **not** an
   unconditional hoist: movie dimensions are not guaranteed uniform across a STAR file and
   the EER path uses `renderer.loadEERGain` with per-movie renderer state.
5. **Do not pursue** `cudaGetDeviceCount` (0.292 s of CUDA runtime init). Moving it only
   re-attributes the cost across the timer boundary and would turn a hard "invalid GPU
   device ID" abort into a silent CPU fallback.

## Integration risks

- **Merge conflict, not semantic conflict.** The change is confined to `src/rwMRC.h`.
  Concurrent Issue #50 work touches `src/acc/cuda/cuda_movie_session.cu` and the
  gain/defect region of `src/motioncorr_runner.cpp`; neither overlaps.
- **`writeMRC` is shared.** It writes the corrected micrograph, `_noDW`, `_PS`, `_EVN`/`_ODD`
  and the rotated gain reference. All exercised above except the even/odd split.
- **The direct-write predicate must not be widened casually.** Adding `SChar` would convert
  a `REPORT_ERROR` into a silent write; adding `Double`/`UChar` would extend it past what
  `writeMRC` can emit. The exclusions are commented in place.
- **Single-precision builds take a different path** for `arms` by design
  (`RELION_SINGLE_PRECISION` keeps calling `computeStddev()`); that path is untested here
  because the project builds `RFLOAT = double`.
- **The tracer is not thread safe** and must never be marked inside an OpenMP region. It is
  compiled out unless `STAGE_TRACE=ON`.
- **Not verified:** the full 24-movie dataset, EER input, explicit defect maps, even/odd
  split, and CPU/streaming fallback paths.

## Limitations

- One movie, one host, one GPU. No 24-movie run.
- Wall-time conclusions are build-specific: resolved unoptimized, not resolved at `-O2`.
- Stage-trace intervals are host wall intervals and may overlap asynchronous CUDA work.
- ~0.06 s of the measured process-level gain is not attributable to a traced interval.
- `-O2 -ffp-contract=off` was checked as output-identical on the matched movie (GPU host,
  CUDA) and on the synthetic fixture (`cpu64`, CPU-only, GCC 13.3, all four arm/config
  combinations). Neither is a substitute for running the full parity suite across the
  24-movie set before changing the default.

## Effect of the 8-CPU cap on these results

The GPU host was subsequently capped to 8 logical CPUs. What that does and does not change:

- **Parity is unaffected.** `--j` fixes the OpenMP team size via `num_threads(n_threads)`
  regardless of how many cores exist, so reduction order, the hot-pixel set and every
  corrected pixel are unchanged. All exactness results carry over.
- **The paired wall-time result survives the cap — measured, not argued.** The n = 15
  series was repeated inside the `taskset -c 96-103` pool, same binaries, same base-first
  ordering, cap the only difference:

  | regime | n | mean delta | median | negative | p |
  |---|---:|---:|---:|---:|---|
  | uncapped, 124 CPUs | 15 | −0.2213 s | −0.220 s | 14/15 | 0.00012 |
  | capped, 8 CPUs | 15 | **−0.1547 s** | −0.160 s | 14/15 | **0.00012** |

  The capped regime is **independently resolved**, which is what makes the comparison
  meaningful rather than a contest between two noise distributions.

  **But the point estimate is 70% of the uncapped effect, and that difference is not
  established**: permutation p = 0.080 on the two delta sets. So this sits between
  *shifted* (baseline moves, effect constant) and *attenuated* (effect itself shrinks), and
  n = 15 per regime is too small to say which. Absence of evidence of a difference is not
  evidence of its absence. **A constrained host should assume the smaller figure**,
  −0.155 s, until someone runs enough pairs to separate the two.

  Also worth noting: the *baseline* was slightly faster under the cap (3.360 → 3.310 s), the
  same direction a sibling task saw much more strongly (2.229 → 2.087 s). The natural
  explanation is that pinning to 8 adjacent logical CPUs removes thread-migration and
  NUMA-crossing cost. **That explanation does not hold for this workload**, and the existing
  `/usr/bin/time -v` records were enough to check it without running anything new:
  involuntary context switches — the migration proxy — are **75 uncapped and 70 capped** for
  the baseline arm. Seventy switches across a 3.3 s run is far too few to account for 50 ms.
  Whatever moved the baseline here, it was not migration. The sibling task's much larger
  142 ms shift may still have a different cause; this only rules it out for this workload.
- **The TIFF decode recommendation does not survive**, measured, not inferred: 0.291 s at 24
  threads uncapped becomes 0.751 s capped, indistinguishable from 8 threads.

Three distinct ways a result can respond to a resource cap, which are worth separating
because they imply different actions (taxonomy developed jointly with the sibling
hot-pixel task, whose own result landed in the middle bucket):

| class | what changes | what to report |
|---|---|---|
| **shifted** | baseline moves, effect size constant | re-baseline the absolutes, recommendation unchanged |
| **attenuated** | effect itself shrinks but stays resolved | **quote the constrained figure** when the deployment is constrained |
| **eliminated** | effect disappears entirely | reclassify as deployment-dependent, not a code-level win |

The MRC change is shifted-or-attenuated (undetermined at n = 15). The TIFF decode-thread
finding is eliminated. Parity results are invariant in all three senses.
- **The build-flag finding should largely survive**, because the `-O0` penalty falls mainly
  on single-threaded host code (the four statistics passes, the MRC write) rather than on
  parallelism — but that is reasoning, not a measurement, and is labelled as such.

## Compute hosts and resource caps

Two hosts, deliberately split, after the shared GPU VM was found to be overloaded:

| Host | Use | Cap |
|---|---|---|
| `4GPUs` (`4-gpu-vm`, 4x A100, 124 cores) | anything GPU-dependent: CUDA builds, benchmarks, traces | **`taskset -c 96-103`** (8 logical CPUs) on the top-level shell, build parallelism <= 8, **one** build or benchmark at a time via `flock /tmp/motioncorr-bench.lock` |
| `cpu64` (`small-refmac-machine`, 64 cores) | CPU-only builds, reference runs, numerical validation | check load first; modest parallelism (`-j 16`, `nice`) |

`taskset` on the top-level shell is the real cap, not an advisory: children inherit the
affinity mask, so OpenMP, `make -j` and `nvcc` are all confined, and `nproc` reports 8 so
CMake's own auto-parallelism also sees the smaller pool. Verified under load — 16 spinning
threads launched inside the wrapper all ran on CPUs 96-103 and consumed 8 cores box-wide.
`/home/alex/MotionCorr-nonkernel-wall/capped.sh` wraps `flock` + `taskset` + the thread
limits together.

Two setup notes for `cpu64`: it has **no `cmake`** (only `make`), installed here into a
user-local venv rather than changing a shared machine system-wide; and its existing
`MotionCorr` directory is a RELION *job output* directory, **not** a Git checkout, so the
branch and fixtures must be staged explicitly.
