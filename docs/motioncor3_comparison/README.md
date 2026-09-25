# Independent comparison: MotionCorr-standalone PR #51 vs upstream MotionCor3

**Date:** 2026-09-24/25 · **Host:** `4GPUs` (`4-gpu-vm`) · **Dataset:** the 24-movie
RELION SPA tutorial subset (EMPIAR-10204, CC0), identical inputs for both arms.

> ### ⚠ VENUE: this is the `4GPUs` shared VM result — HISTORICAL
> Every number in this document was measured on the **`4GPUs` shared VM**:
> **A100 80GB PCIe**, CUDA 12.8, 124 logical CPUs, our work confined to an 8-CPU
> `taskset`, with a **third-party job inside that core mask** for part of the series,
> against **MotionCorr-standalone commit `306bc67`** (the PR #51 head at that time).
>
> A separate comparison is being run on **SCARF Slurm** — **A100-SXM4-40GB**, driver
> 580.178.04, AMD EPYC 7302, 64 CPUs/node, in a **dedicated uncontended allocation**,
> against the **current** PR #51 head `0c7d68f7`. Different GPU memory size, different
> interconnect (SXM4 vs PCIe), different CPU, different commit, different contention
> regime.
>
> **No ratio, speedup or agreement figure may be carried between the two venues.**
> Cite figures from this document as "4GPUs / PCIe-80GB / 306bc67 / contended".



> **This is not a parity test and no bit-level agreement is claimed or implied.**
> The two programs implement different algorithms. They were run with the closest
> equivalent options obtainable, and every option that *cannot* be matched is
> enumerated in §3.2. Agreement is quantified with scale-invariant cross-implementation
> measures (FRC, trajectory RMS), never with byte or pixel equality.

## 0a. CORRECTION (2026-09-25): the headline speed result does not reproduce

**The 1.78x speed advantage reported below does not reproduce on a dedicated node and
must not be cited.** What replaces it is narrower than a causal claim, because the two
sites differ in more than the host.

### What was directly observed

| Site (both arms measured together, same inputs) | MotionCorr-standalone | MotionCor3 1.2.4 | ratio |
|---|---|---|---|
| `4GPUs` shared VM, our commit `306bc67` | 41.67 s | 73.47 s | **1.76x** |
| SCARF dedicated node, our commit `0c7d68f` | 31.51 s | 31.70 s | **1.006x** |

Each row is internally valid: both arms ran on the same machine, same inputs, close in
time. **At 1 GPU on a dedicated node the two implementations are indistinguishable.**

### What is NOT established

It is tempting to write `2.32 / 1.32 = 1.76` and conclude the whole advantage was a host
effect. **That arithmetic is not proof**, for a concrete reason:

* MotionCor3 was the **same commit** (`dd8b6831`) at both sites, so its 73.47 -> 31.70 s
  (2.32x) is a clean site-to-site comparison.
* MotionCorr-standalone was **not**: `306bc67` on 4GPUs versus `0c7d68f` on SCARF. Its
  41.67 -> 31.51 s (1.32x) therefore mixes the host change with ~2 weeks of code change,
  and the two cannot be separated from these data.

So the coincidence between 2.32/1.32 and the original 1.76x is suggestive, not
demonstrative. The defensible statement is: **the sites disagree sharply about the
relative performance of the two tools, and the advantage measured on 4GPUs does not
survive on SCARF.** Attributing that entirely to the host would require re-measuring
`306bc67` on SCARF, or `0c7d68f` on 4GPUs - neither has been done.

### What the stage timers do and do not show

Established, from MotionCor3's own instrumentation (same commit both sites, so this
comparison is clean):

* The gap is entirely inside `Computation time`: 70.71 s vs 16.36 s over 24 movies.
* It is **not** TIFF I/O or page cache - SCARF's TIFF load is *slower* (28.12 vs
  16.75 s) and `File system inputs = 0` at both sites.
* A pure-device stage (local motion correction) costs **0.224 s vs 0.207 s - equal** -
  while a transfer-heavy stage (apply gain) costs 0.15 s vs 0.06 s.
* CPU-seconds are 110 vs 77, only 1.43x, against a 4.3x wall difference.

Together these say the 4GPUs run was **stalling rather than computing**, and that
whatever stalls it does not slow every kernel uniformly.

**The cause is a HYPOTHESIS and remains UNVERIFIED.** Host-to-device transfer latency is
consistent with the stage signature, and NUMA locality is a plausible mechanism (4GPUs
has 2 nodes at distance 20 and `taskset -c 96-103` lies wholly on node 1), but *neither
is established*. Virtualised PCIe and the driver difference (570.86.10 vs 580.178.04)
remain equally open. A direct diagnostic - pinned **and** pageable transfer bandwidth and
latency, varying only the memory node - was designed and then **deliberately not run**,
because foreign jobs came to span the whole 96-103 mask at ~207% CPU and running it would
have degraded a shared machine for another user. It stays unverified until the box is
genuinely free.

Also unexplained: peak RSS 9.06 GB vs 1.84 GB for the same binary and options.

### Other hypotheses eliminated by measurement

* Not MotionCor3's `-O0` host build - its `-O3` binary was measured on 4GPUs at 71.1 s
  median against stock's 73.5 s. Both ~4x SCARF.
* Not GPU contention - all four GPUs read 1 MiB / 0 % immediately before the 75.7 s run.
* Not a degraded PCIe link - 4GPUs GPU 0 negotiates Gen4 x16.
* Not option drift - MotionCor3's printed configuration is byte-identical at both sites.
* Not `-GpuMemUsage` residency - the `GPU n Allocation time` lines are byte-identical.
* Not alignment iteration count - 1985 vs 1983.

### Separately: MotionCor3 is not deterministic

Two identical 24-movie serial runs, same GPU, same process, same binary, agree on only
**9 of 24** aligned sums and 9 of 24 dose-weighted sums. `Patch-Full.log` (global
trajectory) matches **24/24**; `Patch-Patch.log` differs on the same 15 movies. The
nondeterminism is confined to the **local patch path**. Independently reproduced on SCARF
by another session: 7/24 identical, `Patch-Full` 24/24, `Patch-Patch` 9/24.

Median run-to-run relative RMSE is ~3.5e-2, which is **~35x the project's Gate 2
relative-image-RMSE limit of 1e-3**. Any numerical gate against MotionCor3 output that is
tighter than MotionCor3's own reproducibility cannot be satisfied in principle.

This invalidated one of this report's own controls - see the withdrawal notice in
section 5.1. Movies **00021 and 00022 are both in the invariant set of 9**, and they were
the only movies the determinism and batch-composition controls examined, so those
controls ran clean while being structurally unable to observe the condition they
asserted. With 9 of 24 movies invariant, a single-movie control had better than a
one-in-three chance of passing regardless of the truth.

The agreement metrics in section 6 remain valid as single-run measurements, but should be
read knowing that a MotionCor3 rerun moves the local-patch contribution on ~62 % of
movies.

## 0. Summary of findings

1. **Speed — MotionCorr-standalone 306bc67 is 1.78× faster** (median; range 1.68–1.83),
   winning 6 of 6 paired runs. Median 41.7 s vs 73.5 s for 24 movies on one A100.
2. **Memory — MotionCor3 uses 5–6× more host RAM** (8.4–10.4 GB vs 1.68 GB peak RSS).
   This is load-independent and is the more robust of the two performance results.
3. **MotionCor3's unoptimised upstream build does not explain the speed gap.** A
   host-`-O3` rebuild changes wall time by +0.15 s on ~71 s (paired, n = 4) — no effect.
4. **Trajectories agree closely:** global-shift RMS 0.168 px median (max 0.51 px over
   all 24 movies), with the sign convention agreeing on 24/24.
5. **Corrected images agree well to ~5 Å and degrade beyond it:** FRC median 0.953 at
   10 Å, 0.838 at 5 Å, 0.630 at 3 Å, 0.256 at Nyquist (1.77 Å); FRC falls below 0.5 at a
   median of 2.5 Å.
6. **Both arms did the work they were supposed to.** All 24 MotionCorr movies used the
   CUDA path (24/24 emitted the CUDA profile block, 0 fallback warnings) and all 24 kept
   their 5 × 5 local motion model (0 rejections). MotionCor3 flagged 337 of 14 400 patch
   measurements as bad (2.3 %).
7. **Two defects found in upstream MotionCor3** (§8), one of which makes its results
   non-reproducible across invocation styles.

## 1. Identification of the two implementations

### Arm A — MotionCorr-standalone (this repository), PR #51
| Field | Value |
|---|---|
| Repository | `KingAlejandro/MotionCorr-standalone` |
| Pull request | [#51](https://github.com/KingAlejandro/MotionCorr-standalone/pull/51) "feat(cuda): end-to-end GPU residency and fused preprocessing (fixes #50)" |
| Branch | `feat/issue-50-cuda-end-to-end-residency` |
| Commit | `306bc67ecaa142d247ac9cee53b05ae0a3fc116c` (2026-09-24 19:39:06 +0100) — confirmed as PR head via `gh pr view 51 --json headRefOid`; no newer SHA at time of test |
| Base branch | `feat/issue-47-cuda-fft-patch-prep` (not `main`) |
| Provenance | extraction of RELION 5.1 (`3dem/relion` `ver5.1` @ `ad0b230ca22095700f6392479326836efb1c911d`), its *own* MotionCor2-style implementation (`--use_own`) |
| Licence | GPL-2.0-or-later (RELION terms; `LICENSE`, `COPYING`) |
| Build requirements | C++17, CMake >= 3.21, FFTW (float+double), OpenMP, libtiff, libpng, libjpeg, zlib; optional Ghostscript for the summary PDF; optional CUDA via `-DCUDA=ON` |
| Runtime | runs CPU-only by default; `--gpu <id>` selects the experimental CUDA path |

### Arm B — upstream MotionCor3
| Field | Value |
|---|---|
| Repository | `czimaginginstitute/MotionCor3` (Chan Zuckerberg Institute for Advanced Biological Imaging) |
| Commit tested | `dd8b6831ae66ef016fb7ef3b9b6172f8b56c79aa` (2025-10-03), `main` HEAD, commit subject "MotionCor3 1.2.4" |
| Tagged releases | `v1.0.1` (`21c0a05f3a2287ad2b605d261c6c83081240ca45`, 2023-10-26) is the **only** GitHub release. `main` is 4 commits ahead and self-describes as 1.2.4, so "latest official version" and "latest release" are not the same thing here; 1.2.4 was tested as the current upstream source. |
| Licence | BSD-3-Clause, "Copyright 2023 Chan Zuckerberg Institute for Advanced Biological Imaging" (`LICENSE.md`) |
| Build requirements | Linux, NVIDIA GPU, CUDA toolkit, libtiff, pthread. Official recipe `make exe -f makefile11`, overriding `CUDAHOME` (and `CONDA`, which upstream hard-codes to `$HOME/miniconda3` purely as an include/lib prefix). Links `cufft`, `cudart`, `cuda`, `nvToolsExt`, `tiff`. |
| Runtime | **GPU-only — there is no CPU fallback path.** |
| Note on build flags | `makefile11` sets `CFLAG = -c -g -pthread -m64`: the upstream recipe compiles **all host objects with no optimisation flag (-O0)**. Device code is unaffected (it goes through `nvcc -cuda ... -O2` with `-gencode` for sm_70/75/80/86/87/89/90). Both a stock build and a host `-O3` build were produced and timed, because quoting one MotionCor3 wall time without saying which build it came from would be misleading. |
| Vendored binaries | `LibSrc/Lib/libmrcfile.a` and `LibSrc/Lib/libutil.a` are **prebuilt static archives committed to the upstream repository**; the official recipe links them rather than building them from the `LibSrc/Mrcfile` and `LibSrc/Util` sources that are also present. They were used as-is, as the official recipe does. |

**Relationship.** These are not two builds of one program. MotionCor3 is the CZII successor to Shawn Zheng's MotionCor2. Arm A is RELION's *independent reimplementation* of the MotionCor2 *algorithm family*, extracted from RELION 5.1. Bit-level agreement is not expected, is not claimed anywhere in this report, and would in fact indicate an error.
## 2. Environment, hosts and protocol

### Host
All builds and runs were done on the shared GPU host reached by the SSH alias **`4GPUs`** (`4-gpu-vm`).

| | |
|---|---|
| OS / kernel | Ubuntu 24.04.4 LTS, Linux 6.8.0-136-generic |
| CPU | AMD EPYC 7452 32-Core, 124 logical CPUs, 432 GiB RAM |
| GPU | 4 × NVIDIA A100 80GB PCIe, driver 570.86.10. **Only GPU 0 was used, by both arms.** |
| Toolchain | GCC 13.3.0, CUDA 12.8 (V12.8.61) |
| Libraries | libtiff 4.5.1, FFTW 3.3.10, Ghostscript 10.02.1 |

`cpu64` (`small-refmac-machine`) was checked and found healthy (64 cores, load ~2.0, 226 GiB) but was **not** used. The comparison is GPU-dependent on both arms, and the numerical analysis reads ~5.5 GB of corrected micrographs that live on `4GPUs`; the two hosts have no direct route between them, so moving the data would have meant hauling it through a third machine. The analysis therefore ran on `4GPUs`, niced and outside every timed window. This is a deliberate deviation from the "CPU-only work goes to cpu64" convention, recorded here rather than left implicit.

### Resource protocol actually followed
* Every build, run and analysis step ran under **`taskset -c 96-103`** applied to the top-level shell, so children inherit the mask. Verified from inside the lock: `taskset -cp` reported `96-103` and `nproc` reported `8`, meaning CMake and `make -j` also saw the smaller pool. Build parallelism was `-j 8`.
* Every build and every measured run was serialised box-wide behind **`flock /tmp/motioncorr-bench.lock`**. Occupancy was only ever tested with `flock -n`, never by the presence of `/tmp/motioncorr-gpu-timing.lock`, which is an advisory display file with no ownership discipline.
* Measured runs additionally waited for a **settle gate** — `load1 < 2.0` and zero `cc1plus`/`nvcc`/`cicc`/`ptxas` by exact process name (`pgrep -x`, never `-f`, which self-matches) — and the observed settle duration is logged so a long wait is visible rather than absorbed.
* **A genuinely quiet box was not achievable and is not claimed.** The machine is shared with other users whose work is outside this mutex. Every timed run therefore carries a 1 Hz sample of total non-`alex` CPU for its whole duration, reported as `foreign_cpu mean/max`, so a contended run is visible as data instead of hiding inside an arm's mean.

### Coordination
Three other Claude sessions were working the same host concurrently. Two incidents are recorded because they affected data:
1. My first build window released the lock at 23:02:34 and a peer's measurement began at that instant, but load average was still ~6 from my build's decay tail. That peer's first run was contaminated and was discarded on my report. **The flock serialises ownership but not the previous holder's decay tail** — this is why the settle gate exists, and it was added on both sides afterwards.
2. I briefly reasoned that a metrics-only pass "isn't a measurement, so it doesn't need the lock". That is wrong: the mutex is about what work *does to others*, not what it *needs*. A 24-movie GPU run must be serialised regardless of whether it produces a number. Corrected before it caused harm.
## 3. Option matching

### 3.1 Options that were matched

| Quantity | MotionCorr-standalone (RELION `--use_own`) | MotionCor3 1.2.4 |
|---|---|---|
| Input movies | `--i movies.star` (24 rows) | `-InTiff Movies/ -InSuffix .tiff -Serial 1` |
| Gain reference | `--gainref Movies/gain.mrc`, applied by **multiplication** (`motioncorr_runner.cpp:1342`) | `-Gain Movies/gain.mrc -InvGain 0`, also multiplication (`GApplyRefsToFrame.cu:70`) |
| Gain orientation | `--gain_rot 0 --gain_flip 0` | `-RotGain 0 -FlipGain 0` |
| Pixel size | 0.885 Å (STAR optics) | `-PixSize 0.885` |
| Voltage | 200 kV (STAR optics) | `-kV 200` |
| Dose per frame | `--dose_per_frame 1.277` | `-FmDose 1.277` |
| Pre-exposure | `--preexposure 0` | `-InitDose 0` (see §3.2.9 — this option is dead code) |
| Dose weighting | `--dose_weighting` | implied by `-FmDose > 0` and `-PixSize > 0` |
| Patch grid | `--patch_x 5 --patch_y 5` | `-Patch 5 5 0` (0 % overlap) |
| Frame grouping | `--group_frames 1` | `-Group 1 1` |
| Output binning | `--bin_factor 1` | `-FtBin 1` |
| Frames summed | all 24 | `-Throw 0 -Trunc 0 -SumRange 0 0` |
| Aligned (not simple) sum | default | `-Align 1` |
| Shift origin | frame 0 (`cur_xshifts[0] = 0`) | **`-FmRef 1`** — required. MotionCor3's default `-FmRef -1` uses the *centre* frame, which translates its output sum relative to RELION's by a non-integer number of pixels. |
| Alignment reference | leave-one-out: each frame against the sum of the others (`motioncorr_runner.cpp:2728`) | **the same** — `GCorrelateSum2D.cu:25`, `(cSum - cXcf) * conj(cXcf)` |
| CTF estimation | not implemented | **`-Cs 0`** — required. MotionCor3's in-code default is `Cs = 2.7` and CTF estimation runs whenever `Cs > 0.001` (`CFindCtfMain.cpp:28`), despite the help text claiming the default is 0. |
| Dose-selected sum | no such output | **`-SumRange 0 0`** — required. The default `3 25` e/Å² emits an extra `_DWS` sum from a frame subset (`CFmIntParam.cpp:99`). |
| In-frame motion | not implemented | `-InFmMotion 0` |
| Odd/even split | `--even_odd_split` off | `-SplitSum 0` |
| GPU device | `--gpu 0` | `-Gpu 0` |
| Shift sign convention | stores measured displacement, applies its negative (`motioncorr_runner.cpp:2810`) | **the same** (`CCorrectFullShift.cpp:305`) |

### 3.2 Options that CANNOT be matched

These are algorithmic, not configuration, and are why no parity claim is made.

1. **The B-factor is not the same filter — this is the largest unmatched knob.**
   RELION: `exp(-2·B·(ky²/nfy² + kx²/nfx²))` on the full 3710 × 3838 grid (`motioncorr_runner.cpp:2703`).
   MotionCor3: `exp(-0.25·B·(kx² + ky²) / ((cmpX-1)·cmpY))` on its internally binned grid (`GCorrelateSum2D.cu:45`).
   Different coefficient, different normalisation, different grid. At B = 150 and 0.885 Å/px the e⁻¹ points are roughly **31 Å (RELION) vs 14 Å (MotionCor3)**. `-Bft 150 150` matches the *number*, not the filter. A sensitivity arm at MotionCor3's own default `-Bft 500 100` is therefore reported alongside, so the reader can see how much of any disagreement this one knob explains.
2. **MotionCor3 ramps the B-factor down during iteration** (`CIterativeAlign.cpp:126`, `fBFactor -= 2` per iteration, floor 20); RELION computes its weight once before the loop. Iteration count and filter are therefore coupled in one tool and independent in the other.
3. **MotionCor3 smooths and despikes the global trajectory; RELION does not.** A 3-tap `[0.3, 0.4, 0.3]` smoother (`CStackShift.cpp:189`), then `RemoveSpikes` plus a second `[0.25, 0.5, 0.25]` pass (`CIterativeAlign.cpp:148`). A non-zero trajectory RMS between the arms is therefore *expected* and is not evidence that either is wrong.
4. **Different measurement grids.** MotionCor3 always bins the cross-correlation so its long axis is ≈ 2048 (`CBufferPool.cpp:225`), regardless of `-FtBin`, and the x/y bin factors differ slightly (anisotropic). RELION keeps Fourier data at full resolution and downsamples only the CC map. Peak-search windows also differ (≈ ±116 raw px vs ≈ ±47).
5. **Solver budget.** RELION `--max_iter 5` with a hardcoded 0.5 px tolerance; MotionCor3 `-Iter 15 -Tol 0.1`. Both left at their own defaults.
6. **Patch motion model.** RELION fits one global polynomial (3rd order in time × 2nd order in x,y) across all 25 patches and **discards it entirely** — falling back to global-only correction — if fewer than 19 patches converge, if a neighbouring-pixel delta exceeds 3 px, or if the fit RMSD exceeds 10 px. MotionCor3 instead flags individual bad patches and interpolates a shift field. Both arms' logs are scraped for how often each fallback fired.
7. **Interpolation.** RELION applies the local model by real-space bilinear resampling; MotionCor3 by a GPU patch-shift kernel. Different high-frequency transfer, which shows up in the FRC near Nyquist regardless of alignment agreement.
8. **MotionCor3 clamps its output to non-negative** (`CCorrectFullShift.cpp:172`, `GPositivity2D`), on both the plain and the dose-weighted sum. RELION writes the raw float sum. This changes the pixel distribution and every moment-based statistic.
9. **Dose weighting agrees in formula but not in the DC term.** Critical-dose constants and the 200 kV factor match. But MotionCor3 skips index 0 (`GWeightFrame.cu:41`), leaving the DC unweighted, while RELION weights and normalises it — so the two dose-weighted micrographs differ by a large constant offset. Separately, `-InitDose` is parsed, printed, and **never read** anywhere in MotionCor3; RELION additionally adds any per-micrograph `_rlnMicrographPreExposure` from the STAR.
10. **Defect handling.** RELION marks every `gain == 0` pixel bad and inpaints it from a random good neighbour seeded by `--seed 1`; MotionCor3 has no gain-zero rule (those pixels simply become 0.0) and runs its own hot-pixel and anomalous-patch detector.
11. **Threading and pipelining.** RELION takes `--j 8` and processes movies one at a time; MotionCor3 exposes no thread count and runs a 3-stage read/compute/save pipeline that overlaps across movies. Equal CPU *allocation* was enforced with `taskset`; equal CPU *use* cannot be.
12. **Ancillary outputs.** RELION also writes per-movie EPS plots and a Ghostscript `logfile.pdf`; MotionCor3 writes text logs. MotionCorr wall time is therefore reported both with and without `--skip_logfile`.

### 3.3 Corrections to assumptions made during design

Two differences that were assumed and turned out **not** to be differences, recorded so they are not repeated:

* **`--early_binning` is OFF here, not on.** `motioncorr_runner.cpp:140` forces it off whenever `bin_factor == 1`, which is this configuration.
* **The alignment reference is matched.** Both tools use a leave-one-out reference against the running aligned sum. Only the *shift origin* differed, and `-FmRef 1` fixes that.
## 4. How the two arms were compared

Because the algorithms differ, every metric is chosen to be meaningful *across*
implementations. No metric here tests bit parity, and none is capable of showing it.

### 4.1 Trajectory
RELION writes per-frame global shifts to the `data_global_shift` block of each
per-micrograph STAR file; MotionCor3 writes them to `<base>-Patch-Full.log`. Both
define the trajectory only up to a constant, so both are mean-centred before
comparison. Both were verified in source to store the *measured* displacement and
apply its negative, so the expected relation is `(+x, +y)`; all four axis-flip
combinations are evaluated and anything other than `(+,+)` is reported as a finding
rather than silently absorbed as a fitted sign.

Two properties of this metric must be stated with it:
* MotionCor3 truncates its global shift to 0.01 px (`CStackShift::TruncateDecimal`),
  giving the metric a hard floor near 0.003 px.
* MotionCor3 smooths its global trajectory twice and despikes it; RELION does not.
  **A non-zero trajectory RMS between these two tools is expected and is not by itself
  evidence that either is wrong.**

### 4.2 Corrected image
The primary metric is the **Fourier Ring Correlation between the two corrected sums**,
which is invariant to scale and offset and localises *at which spatial frequency* the
implementations stop agreeing — something a single scalar RMSE cannot do.

Sub-pixel registration is applied first and is not optional. With `-FmRef 1` the two
shift origins match, but any residual offset must still be removed in Fourier space:
half a pixel of misregistration alone takes FRC-at-Nyquist from 1.00 to 0.49, so an
unregistered comparison would report a resolution-limited disagreement between two
*identical* images. The offset is estimated by upsampled-DFT phase correlation,
applied as a Fourier shift, and the registered crop is then trimmed inward because a
Fourier shift is circular. The fitted offset is itself reported per movie.

Implementation details that matter:
* Ring sums down-weight the `kx = 0` and `kx = Nyquist` columns by 0.5, since an
  `rfft2` half-plane holds both members of each Hermitian pair in those columns.
* An FRC threshold crossing is only declared if the curve stays below the threshold
  for three consecutive rings, so one noisy ring cannot report a spuriously
  pessimistic resolution.
* Header `amin`/`amax`/`amean` are **recomputed from pixels** for both arms.
  MotionCor3's header statistics are read from a device buffer that is never written
  before the sum is saved (`CSaveSerialCryoEM.cpp:231`), i.e. they are uninitialised
  VRAM and must not be compared.
* Pearson r and normalised residual RMSE were dropped. On two corrected sums of the
  same movie the electron-shot noise realisation is shared, so r saturates: it reads
  0.94 even for identical images misregistered by half a pixel, a condition that has
  already destroyed half the FRC. `linear_fit_scale`/`offset` are retained as
  diagnostics, because they surface MotionCor3's non-negativity clamp and its
  unweighted DC term.

### 4.3 Validity gates run alongside
* **Batch-position control.** One movie processed alone is compared pixel-for-pixel
  against the same movie processed inside the 24-movie batch. Source reading shows
  MotionCor3's defect correction is a deterministic function of pixel index with no
  RNG state, but that shows only that there is no *seed* — not that no other per-movie
  state carries. The control tests it instead of arguing it.
* **Fallback scraping.** MotionCorr's CUDA path has CPU fallback branches that announce
  themselves only as a `WARNING` in a per-movie log; a partial fallback would mean the
  timing and the "CUDA path" claim are both wrong. RELION also discards its 5 × 5 local
  motion model entirely — correcting with the global trajectory alone — if too few
  patches converge or the fit is too steep. Both conditions are counted across all 24
  movies and reported, because a movie that fell back is being compared as "local
  correction versus none".
* **B-factor sensitivity.** Since `--bfactor 150` and `-Bft 150 150` are demonstrably
  different filters, MotionCor3 is additionally run at its own default `-Bft 500 100`
  so the reader can see how much of any disagreement that single unmatchable knob
  accounts for.

### 4.4 Wall time
Timed runs use a **paired design with the arm order alternating within each pair**, and
the ordering label is kept per pair. This cancels slow drift in third-party load within
each pair, and lets the positional advantage *P* (the benefit to whichever arm runs
second, mostly input page-cache warming) be recovered afterwards from the same data as
`observed = E ± P`, at no extra cost.

Every timed run is validated before its time is used: a run that did not exit 0 **and**
did not produce 24 corrected micrographs is recorded as `INVALID` and excluded. A
crashed run is fast, and an unvalidated timing series rewards crashing.

All wall times are **cache-warm**. The 3.0 GB dataset was already fully resident in page
cache (432 GiB of RAM, `File system inputs = 0` on every run including the first), and
dropping caches requires root. No cold-start number is claimed.
## 5. Validity controls

Three controls were run before any conclusion was drawn. One of them failed on its
first design, and the failure was in the control, not the tool.

### 5.1 Batch-position and determinism (MotionCor3)

Reading `BadPixel/GCorrectBad.cu:56` shows MotionCor3's defect correction is a
deterministic function of the pixel's linear index (`next = i * 109 + 619`, advanced by
`*= 997`), with `curand.h` included but never called — no seed, no stream, no carried
state. That establishes there is no RNG. It does **not** establish that no other
per-movie state carries, so the property was tested rather than argued.

| Control | Pixels | Global traj. | Patch traj. |
|---|---|---|---|
| Same 24-movie serial batch, run twice | identical | identical | identical |
| 2-movie serial batch vs 24-movie serial batch | identical | identical | identical |
| Single-movie mode (`-Serial 0`) vs 24-movie serial batch | **differ, 10.1 % relative RMSE** | identical | **differ** |

> ### WITHDRAWN (2026-09-25): this control was structurally blind
> **The conclusion below is wrong.** It was drawn from **movie 00021 only**
> (`M1=$(sed -n 1p movie_bases.txt)`). Repeating the comparison across **all 24
> movies** shows MotionCor3 is **not** deterministic:
>
> | Two identical 24-movie serial runs, same GPU, same process, same binary | identical | differs |
> |---|---|---|
> | aligned sums (pixels) | 9/24 | **15/24** |
> | dose-weighted sums (pixels) | 9/24 | **15/24** |
> | `Patch-Full.log` (global trajectory) | **24/24** | 0/24 |
> | `Patch-Patch.log` (local patch shifts) | 9/24 | **15/24** |
>
> Differing movies: 00024 00025 00027 00028 00029 00030 00031 00035 00036 00037
> 00040 00042 00043 00047 00049 - the same 15 in every category. Global alignment
> is perfectly reproducible; **the local patch path is not.**
>
> Movie 00021 is in the invariant 9, so the control ran clean and could not have
> observed the condition it asserted. The 2-movie batch-composition control is blind
> for the same reason: **both** movies it used (00021, 00022) are in the invariant set.
>
> **The batch-composition conclusion is withdrawn, not downgraded.** Once run-to-run
> nondeterminism exists, a difference between two compositions cannot be attributed to
> composition - repeats of the *same* composition also differ. Isolating composition
> requires repeats within each composition and a comparison of distributions.
>
> This does not affect the wall-time findings, which rest on timers rather than output
> equality, nor the agreement metrics in section 6, which compare one MotionCorr run
> against one MotionCor3 run - though section 6 should be read knowing that a
> MotionCor3 rerun would move the local-patch contribution on ~62% of movies.

**Superseded conclusion (retained for the record):** *MotionCor3 in serial mode is
deterministic and independent of batch composition, so the 24-movie batch design is
valid.*

The first version of this control compared single-movie mode against the serial batch
and reported a difference, which looked like batch-position dependence. It was not:
those two invocation modes use different save/correct code paths
(`CSaveSingleCryoEM` vs `CSaveSerialCryoEM`), so that comparison confounded two
variables and could not answer the question it was built to answer. The serial-vs-serial
controls above separate them.

**Incidental finding worth reporting upstream:** MotionCor3 produces *materially
different corrected images* for the same movie with the same options depending on
whether it is invoked on a single file or as part of a serial batch — max absolute
difference 4.98 on a sum with σ ≈ 1.0, 99.98 % of pixels differing, 10.1 % relative
RMSE. The global trajectory is byte-identical in both cases and the bad-patch count is
the same (13 of 600), so the divergence arises in patch measurement/application, not in
global alignment. This is not a defect in either arm of this comparison — both arms here
use one consistent mode — but it means a MotionCor3 result is not reproducible across
invocation styles.

### 5.2 Fallback scraping (both arms)
MotionCorr's CUDA path contains CPU fallback branches that announce themselves only as a
`WARNING` in a per-movie log, and RELION discards its 5 × 5 local motion model entirely —
correcting with the global trajectory alone — if too few patches converge, if a
neighbouring-pixel delta exceeds 3 px, or if the fit RMSD exceeds 10 px. Either
condition would mean a movie is being compared as "local correction versus none", or
that the timed path is not the CUDA path under review. Both are counted across all 24
movies; see §6.
## 6. Results — agreement between the two implementations

All 24 movies completed on both arms with zero analysis errors and **zero sign-convention
disagreements** (the expected `(+x, +y)` relation held on all 24, so no per-movie sign was
fitted).

### 6.1 Summary across 24 movies (matched arm, `-Bft 150 150`)

| Quantity | Median | Min | Max |
|---|---|---|---|
| Global-shift trajectory RMS (px) | **0.1677** | 0.1351 | 0.2259 |
| Global-shift max per-frame difference (px) | 0.3269 | 0.2245 | 0.5074 |
| Residual image offset after `-FmRef 1`, dy (px) | +0.680 | +0.160 | +0.940 |
| Residual image offset after `-FmRef 1`, dx (px) | +0.325 | −0.020 | +1.030 |
| FRC at 10 Å (dose-weighted) | **0.9532** | 0.9285 | 0.9710 |
| FRC at 5 Å (dose-weighted) | **0.8380** | 0.7698 | 0.8936 |
| FRC at 3 Å (dose-weighted) | 0.6301 | 0.4697 | 0.7458 |
| FRC at Nyquist 1.77 Å (dose-weighted) | 0.2558 | 0.0186 | 0.5640 |
| Resolution where FRC drops below 0.5 (Å) | **2.505** | 1.783 | 3.188 |
| FRC at 5 Å (unweighted) | 0.8150 | 0.7190 | 0.8928 |
| FRC at Nyquist (unweighted) | 0.1596 | 0.0072 | 0.3463 |

**Reading:** the two implementations produce corrected micrographs that agree very well
at low and medium resolution and diverge progressively towards Nyquist. The divergence
is expected and attributable to documented algorithmic differences — different patch
motion models (§3.2.6), different interpolants for applying the local correction
(§3.2.7), and different defect handling (§3.2.10) — not to either being wrong.

The **residual offset is systematically positive in dy** (median +0.68 px, positive on
all 24 movies). `-FmRef 1` aligns the *shift origin*, so this residual is a genuine
sub-pixel convention difference between the two tools, not noise. It is removed before
every image metric; had it not been, it alone would have cost roughly half the FRC at
Nyquist.

### 6.2 Per-movie results (matched arm)

| Movie | traj RMS (px) | traj max (px) | offset dy,dx (px) | FRC 10 Å | FRC 5 Å | FRC 3 Å | FRC Nyq | FRC<0.5 (Å) | noDW 5 Å | noDW Nyq |
|---|---|---|---|---|---|---|---|---|---|---|
| 20170629_00021 | 0.1527 | 0.2898 | +0.16, +0.85 | 0.928 | 0.793 | 0.624 | 0.499 | 1.83 | 0.790 | 0.061 |
| 20170629_00022 | 0.1657 | 0.3181 | +0.86, +0.32 | 0.954 | 0.843 | 0.636 | 0.252 | 2.50 | 0.812 | 0.102 |
| 20170629_00023 | 0.2259 | 0.4272 | +0.79, +0.15 | 0.961 | 0.860 | 0.664 | 0.483 | 1.78 | 0.797 | 0.222 |
| 20170629_00024 | 0.1690 | 0.3151 | +0.55, +0.36 | 0.940 | 0.807 | 0.530 | 0.187 | 2.90 | 0.852 | 0.272 |
| 20170629_00025 | 0.2081 | 0.4524 | +0.82, +0.53 | 0.934 | 0.791 | 0.547 | 0.260 | 2.64 | 0.719 | 0.198 |
| 20170629_00026 | 0.1584 | 0.3626 | +0.79, +0.26 | 0.934 | 0.844 | 0.680 | 0.391 | 2.23 | 0.735 | 0.007 |
| 20170629_00027 | 0.1854 | 0.2891 | +0.53, -0.02 | 0.955 | 0.815 | 0.525 | 0.067 | 3.03 | 0.817 | 0.146 |
| 20170629_00028 | 0.1737 | 0.3565 | +0.84, +0.02 | 0.953 | 0.820 | 0.571 | 0.212 | 2.79 | 0.814 | 0.144 |
| 20170629_00029 | 0.1459 | 0.2548 | +0.78, +0.44 | 0.953 | 0.894 | 0.734 | 0.356 | 2.12 | 0.803 | 0.019 |
| 20170629_00030 | 0.2038 | 0.3464 | +0.45, +0.17 | 0.970 | 0.888 | 0.746 | 0.465 | 1.91 | 0.859 | 0.278 |
| 20170629_00031 | 0.1476 | 0.2647 | +0.31, +0.52 | 0.953 | 0.814 | 0.575 | 0.128 | 2.77 | 0.816 | 0.121 |
| 20170629_00035 | 0.2155 | 0.3272 | +0.94, +0.59 | 0.971 | 0.879 | 0.725 | 0.439 | 1.94 | 0.852 | 0.213 |
| 20170629_00036 | 0.1766 | 0.3751 | +0.75, +0.31 | 0.948 | 0.837 | 0.650 | 0.341 | 2.26 | 0.801 | 0.075 |
| 20170629_00037 | 0.1865 | 0.4135 | +0.69, +0.40 | 0.956 | 0.775 | 0.470 | 0.019 | 3.19 | 0.822 | 0.167 |
| 20170629_00039 | 0.1598 | 0.3946 | +0.68, +0.12 | 0.945 | 0.770 | 0.474 | 0.191 | 3.14 | 0.844 | 0.225 |
| 20170629_00040 | 0.1818 | 0.3266 | +0.59, +0.34 | 0.955 | 0.838 | 0.584 | 0.088 | 2.74 | 0.814 | 0.098 |
| 20170629_00042 | 0.1433 | 0.2832 | +0.29, +0.17 | 0.970 | 0.871 | 0.705 | 0.301 | 2.24 | 0.833 | 0.197 |
| 20170629_00043 | 0.1351 | 0.2245 | +0.92, +1.03 | 0.951 | 0.838 | 0.689 | 0.564 | — | 0.809 | 0.162 |
| 20170629_00044 | 0.2181 | 0.5074 | +0.68, +0.44 | 0.951 | 0.829 | 0.536 | 0.121 | 2.82 | 0.825 | 0.081 |
| 20170629_00045 | 0.1643 | 0.3038 | +0.50, +0.20 | 0.964 | 0.864 | 0.659 | 0.208 | 2.42 | 0.848 | 0.237 |
| 20170629_00046 | 0.1664 | 0.3920 | +0.21, +0.09 | 0.944 | 0.848 | 0.689 | 0.455 | 1.95 | 0.802 | 0.066 |
| 20170629_00047 | 0.1963 | 0.3222 | +0.47, +0.33 | 0.942 | 0.829 | 0.581 | 0.203 | 2.54 | 0.804 | 0.157 |
| 20170629_00048 | 0.1419 | 0.2629 | +0.81, +0.41 | 0.966 | 0.875 | 0.693 | 0.346 | 2.16 | 0.874 | 0.315 |
| 20170629_00049 | 0.1617 | 0.4220 | +0.38, +0.26 | 0.962 | 0.841 | 0.574 | 0.205 | 2.90 | 0.893 | 0.346 |

### 6.3 B-factor sensitivity

The nominally "matched" `-Bft 150 150` is **not** the same filter as RELION's
`--bfactor 150` (§3.2.1). Running MotionCor3 at its own default `-Bft 500 100` instead:

| | matched `-Bft 150 150` | MotionCor3 default `-Bft 500 100` |
|---|---|---|
| Trajectory RMS (px, median) | 0.1677 | 0.1606 |
| FRC at 5 Å (median) | 0.8380 | **0.8584** |
| FRC at 3 Å (median) | 0.6301 | **0.6520** |
| FRC at Nyquist (median) | 0.2558 | **0.2811** |
| Movies never dropping below FRC 0.5 | 1 / 24 | **7 / 24** |

**MotionCor3 configured with its own default B-factor agrees with MotionCorr slightly
*better* than when given RELION's nominal value of 150.** The effect is small
(≈ +0.02 FRC) but it is consistent across every metric and it is in the opposite
direction to what "we matched the B-factor" would predict. This is direct evidence that
copying the number across does not transfer the filter, and it is why the report does
not claim the B-factor was matched.

### 6.4 Validity gates

| Gate | Result |
|---|---|
| MotionCorr movies that used the CUDA path | **24 / 24** (CUDA profile block present) |
| MotionCorr CUDA→CPU fallback warnings | **0** |
| MotionCorr movies where the 5 × 5 local motion model was rejected | **0 / 24** |
| MotionCorr hot pixels detected and replaced | 57–77 per movie |
| MotionCor3 patch measurements flagged bad | 337 / 14 400 (2.3 %), 0–38 per movie |

The first three matter: had MotionCorr silently fallen back to CPU on any movie, the
timing would not describe the CUDA path under review; had the local model been rejected
on any movie, that movie would have been compared as "local correction versus none".
Neither happened.

### 6.5 Intensity scale
The dose-weighted sums differ in absolute scale by a factor that is **not** a free
parameter. Across all 24 movies the ratio of MotionCor3's DW mean to MotionCorr's is
**4.89908 (min 4.89898, max 4.89922)** against √24 = 4.89898 — i.e. exact to five
significant figures on every movie. RELION weights and normalises the DC term by `1/sqrt(Σw²)`, and at
zero spatial frequency all 24 frame weights are 1, so DC is divided by √24. MotionCor3
skips index 0 entirely (`GWeightFrame.cu:41`) and leaves DC unweighted. Both conventions
are defensible; they are not the same, and any pipeline consuming both must not assume a
common scale.

Relatedly, MotionCor3's unweighted sums contain **exactly-zero pixels** (median 1.97e-5
of the frame, max 2.38e-5 — roughly 280–340 pixels) while MotionCorr's contain **none**
on any movie. This is the predicted consequence of §3.2.10: RELION marks every
`gain == 0` pixel bad and inpaints it, whereas MotionCor3 has no gain-zero rule and those
pixels simply become 0.0 after the multiply.
## 7. Wall time

All figures below come from runs that exited 0 **and** produced 24 corrected
micrographs; a run failing either check is recorded `INVALID` and excluded. All 20
runs in the main series passed. All times are **cache-warm** (`File system inputs = 0`
on every run; the 3.0 GB dataset is fully page-resident in 432 GiB of RAM and dropping
caches requires root).

### 7.1 MotionCorr-standalone 306bc67 vs MotionCor3 1.2.4 — paired, n = 6

| Pair | Order | MotionCorr | MotionCor3 | Diff | Ratio | foreign CPU mean/max (mc / mc3) |
|---|---|---|---|---|---|---|
| 1 | MC first | 40.61 s | 73.45 s | +32.84 s | 1.809 | 6.1/10.2 — 7.9/132.1 |
| 2 | MC3 first | 42.40 s | 77.49 s | +35.09 s | 1.828 | 5.9/6.8 — 7.8/136.3 |
| 3 | MC first | 40.78 s | 72.86 s | +32.08 s | 1.787 | 6.2/9.8 — 16.4/459.3 |
| 4 | MC3 first | 41.98 s | 74.22 s | +32.24 s | 1.768 | 6.5/7.8 — 6.1/8.9 |
| 5 | MC first | 41.37 s | 72.35 s | +30.98 s | 1.749 | 6.4/10.2 — 8.6/125.3 |
| 6 | MC3 first | 43.87 s | 73.48 s | +29.61 s | 1.675 | 310.5/594.3 — 11.8/342.9 |

**MotionCorr-standalone 306bc67 is faster on this workload by a median factor of
1.78× (range 1.68–1.83), winning 6 of 6 pairs.** Median difference 32.2 s, mean
32.1 s, sd 1.8 s.

Order decomposition, `observed = E ± P`:
* **E (true effect) = +32.14 s** — MotionCor3 slower.
* **P (positional bias) = −0.17 s** — negligible here, as expected for two arms that
  both read the same already-warm inputs.

n = 6 is sufficient *for this effect*: 32 s on runs of 40–77 s is a ~1800 % effect
against a per-run spread of ~2 %. (The n ≥ 40 paired requirement recorded for this host
applies to ~40 ms effects on a ~2 s process — four orders of magnitude finer.)

### 7.2 Peak memory — the larger and more robust difference

| Arm | Peak RSS |
|---|---|
| MotionCorr-standalone 306bc67 | **1.68 GB** |
| MotionCor3 1.2.4 | **8.4 – 10.4 GB** |

MotionCor3 uses roughly **5–6× the host memory**. This difference does not depend on
machine load at all, so it is more robust than the timing result.

### 7.3 Does MotionCor3's unoptimised host build explain the gap? No.

Upstream's `makefile11` compiles all host objects with no `-O` flag. A host-`-O3`
variant was built and compared against the stock build in a **paired, order-alternating
series**:

| | |
|---|---|
| E (true effect of host `-O3`) | **+0.15 s** on a ~71 s run — no effect |
| P (positional bias) | −1.54 s |
| `-O3` faster in | 2 of 4 pairs |

**Host optimisation makes no measurable difference**, which is consistent with
MotionCor3 being GPU/pipeline-bound (150–157 % CPU against 800 % available). So the
1.78× gap is *not* an artifact of comparing an `-O3` binary against an `-O0` one.

This sub-result also demonstrates why the alternating design was used: the positional
bias (−1.54 s) is **ten times larger than the effect** (+0.15 s). An unpaired
stock-then-`-O3` series would have reported `-O3` as ~1.4 s faster, and that conclusion
would have been an artifact of run order.

### 7.4 Ancillary output is not the explanation either
MotionCorr additionally writes per-movie EPS plots and a Ghostscript `logfile.pdf`,
which MotionCor3 does not. Removing that work (`--skip_logfile`, n = 4) gives a median
of 40.66 s against 41.67 s — about 1 s, i.e. it *understates* MotionCorr's advantage by
roughly 2 %.

### 7.5 What the timing comparison is and is not
The two tools are **not doing the same amount of solver work**. MotionCor3 runs at its
default `-Iter 15`; RELION at its default `--max_iter 5`. This is a comparison of *each
tool as its authors configure it by default*, not of two implementations of one
algorithm at equal work. Forcing `-Iter 5` was rejected as a "match" because MotionCor3
couples its B-factor to the iteration count (`CIterativeAlign.cpp:126`), so capping
iterations changes its filter as well as its budget.

### 7.6 Contention
A third-party job (`ryz18496`, two Python processes, ~720 % CPU combined) started during
phase 3 and was present for the `--skip_logfile` and host-`-O3` arms. It did **not**
measurably affect the results, and the data contain their own control: MotionCorr ran at
40.58/40.85/40.74/40.49 s under ~730 % foreign load versus 40.61/40.78/41.37 s under
~6 %. The foreign job lands on CPUs outside the `96-103` mask, so it competes for memory
bandwidth and PCIe but not for the allocated cores. This is reported rather than
suppressed because "we held a mutex" does not make a shared box quiet.
## 8. Defects found in upstream MotionCor3 1.2.4

Both were found while building this comparison and are reported because they affect
anyone comparing against, or consuming output from, MotionCor3.

1. **Corrected images depend on invocation style.** The same movie, with identical
   options, processed on its own (`-Serial 0`) versus inside a serial batch
   (`-Serial 1`), yields different corrected images: 99.98 % of pixels differ, max
   absolute difference 4.98 on a sum with σ ≈ 1.0, relative RMSE 10.1 %. The global
   trajectory is byte-identical and the bad-patch count is identical, so the divergence
   is in patch measurement or application. Serial mode itself is fully deterministic and
   independent of batch composition (§5.1), so this is specifically a single-versus-batch
   path difference. **A MotionCor3 result is therefore not reproducible across invocation
   styles.**
2. **MRC header statistics are uninitialised memory.** `CSaveSerialCryoEM.cpp:231-233`
   computes `amin`/`amax`/`amean` from `m_gfImg`, a device buffer allocated in `mInit()`
   and never written before the sum is saved — the actual image is a host pointer passed
   straight to the writer, and the only code that fills `m_gfImg` (`mSaveStack`) runs
   afterwards. The header statistics of every MotionCor3 sum are therefore garbage (stale
   VRAM). This report recomputes all statistics from pixel data for both arms.

Also worth noting, though not a defect: upstream's `makefile11` compiles all host
objects with no optimisation flag, and links prebuilt static archives
(`LibSrc/Lib/*.a`) that are non-PIE and therefore fail to link on a modern
PIE-by-default distribution. See §2 for the build deviation this forced.

## 9. Limitations

* **Wall times are cache-warm only.** The dataset was fully page-resident and dropping
  caches requires root, so no cold-start figure is available for either arm.
* **A quiet box was not obtainable.** The host is shared; a third-party job at ~720 % CPU
  was present for part of the series. Its effect was measured rather than assumed (§7.6)
  and found to be negligible for the allocated cores, but this is a measured bound, not
  an absence of contention.
* **Equal work was not enforced and could not be.** Each tool ran at its own default
  solver budget (§7.5). The speed result compares default configurations, not equal
  computation.
* **Single host, single GPU, single dataset.** All results are for one A100 under an
  8-CPU cap on one 24-movie dataset. Nothing here should be extrapolated to other GPUs,
  other movie geometries, or multi-GPU operation.
* **No ground truth.** This measures agreement *between* two implementations, not the
  accuracy of either. A disagreement identifies which frequencies they treat differently;
  it cannot say which is closer to the true motion. Establishing that would need a
  synthetic movie with a known applied shift field, which was outside this task's scope
  and is the single most valuable follow-up.
* **`--early_binning` is off** in this configuration (forced off by `--bin_factor 1`), so
  these results do not characterise the binned-alignment path.

## 10. Reproducing this

All scripts are in this directory. On `4GPUs`, from `/home/alex/mc3-compare`:

```sh
# build both arms (inside the bench flock, 8-CPU cap)
flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash build_all.sh
flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash build_mc3_all.sh

# controls + metrics outputs (no timing produced, so no settle gate)
flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash run_all.sh 0

# paired timed series (settle gate + 1 Hz foreign-load sampling)
flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash run_phase2.sh 6 4

# analysis (unlocked would perturb others; run it inside the lock too)
flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash analyse.sh
```

Exact commands for both arms are in §3.1; binary and input SHA-256 values are in §1
and are re-emitted at the top of every run log.

### Artifacts in this directory
| File | Contents |
|---|---|
| `compare_matched.json` | per-movie metrics, matched arm (`-Bft 150 150`) |
| `compare_bftdefault.json` | per-movie metrics, MotionCor3 default `-Bft 500 100` |
| `scrape.json` | per-movie fallback / hot-pixel / bad-patch counts, both arms |
| `output_manifest.txt` | SHA-256 prefix, size and path of all 173 output files |
| `timing_series.log` | phase 2/3 timed runs with foreign-load samples |
| `timing_bfactor_and_analysis.log` | paired stock vs host-`-O3`, plus analysis output |
| `controls_and_metrics.log` | batch-position controls and the metrics run |

## 11. Recommended follow-up

1. **Add a synthetic ground-truth arm.** Apply a known per-frame shift field to a static
   micrograph, Poisson-sample to the real dose, and score both tools *against truth*.
   That converts "they differ by X" into "A's error is X, B's is Y", which is the only
   form in which a two-implementation comparison is decisive.
2. **Add a same-binary CPU-vs-CUDA arm.** That is the only pairing where near-exact
   agreement is a meaningful gate and a disagreement is unambiguously a bug in PR #51.
3. **Report the two MotionCor3 defects upstream** (§8).
