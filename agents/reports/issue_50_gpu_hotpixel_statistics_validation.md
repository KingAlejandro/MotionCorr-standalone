# Issue #50 / PR #51 follow-on: GPU hot-pixel statistics — validation report

**Measured branch**: `t3code/gpu-hot-pixel-optimization` at `d5c3deb` (production changes from `a5a4816` and `dd59245`)
**Measured baseline**: `a11f2f1` (earlier PR #51 head)
**Integration**: the two production commits were cherry-picked onto PR #51 head `306bc67`. Review restored the original serial gain-zero mask and made both failed-download paths consistent. Final review replaced the float-narrowing Guard 2 with unconditional host fallback whenever Gaussian replacement is reachable. The original matched measurements below predate these final changes; see the final-head validation near the end of this report.
**Design**: `agents/designs/issue_50_gpu_hotpixel_statistics.md`
**Host**: `4GPUs` (4-gpu-vm), A100 80GB PCIe, GPU 0
**Builds**: both arms `cmake -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_BUILD_TYPE=Release`,
verified `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`

The original measured branch was isolated from PR #51 during validation.

---

## 1. What changed

The resident CUDA path downloaded the full unaligned sum (54.32 MiB) only so the host could
reduce it to `mean`/`std`, derive `mean + 6*std`, and scan for above-threshold pixels. All three
now happen on the device; only a sparse ascending index list returns.

Exactness does not rest on reproducing the host reduction bitwise — that is ill-posed, because the
host reduction is an OpenMP `reduction(+:)` whose result depends on `--j`. It rests on the fact
that `mean`/`std` are consumed in only three places, and only two are observable:

- the threshold comparison, protected by an on-device **guard-band count**;
- `rnd_gaus(frame_mean, frame_std)`, reachable only where some bad pixel has `n_ok <= 6`, which is
  a pure function of `bBad` geometry and is therefore decided before any RNG draw is consumed;
- the log line, which is not covered by any gate.

Any guard failing, a non-finite moment, a CUDA error, or hit-buffer overflow re-runs the original
host scan verbatim.

## 2. Supporting measurements (standalone harness, A100 host, g++ -O2 -fopenmp, N = 3710x3838)

These informed the design and are reported because they correct two widely-quoted premises.

| Question | Measured |
|---|---|
| Is the host reduction reproducible run-to-run at fixed `--j`? | **Yes.** 10/10 bitwise identical at `--j 8`; 3/3 at `--j 1`. |
| Is it reproducible *across* `--j`? | **No.** `std` = 2.8866805473739832 at `--j 1` vs 2.8866805473739943 at `--j 8`; threshold 40.319489494872286 vs 40.319489494872357. Bit-identity is only ever defined **per `--j`**. |
| Can libgomp's reduction be emulated bitwise? | **No, not robustly.** Contiguous-chunk partials combined by libgomp's own reduction matched `mean` at every T, but `std` matched only at T = 1,2,3,4,5,7,8 and **differed at T = 6,12,16,32**. It matches at T=8 — the benchmark configuration — which is precisely the trap. This approach was abandoned. |
| What does the removable host work actually cost? | Two reductions plus threshold scan: **39 ms at `--j 1`, ~20 ms at `--j 8`**. Not the 0.186 s sometimes quoted for the whole `TIMING_DETECT_HOT` stage, which also covers the `bBad` allocation, `fillDefectMask`, and the serial gain-zero scan. |

## 3. Exactness results — bit-identical to `a11f2f1`

Comparison method: MRC pixels from byte 1025 onward and core header bytes 0-223 compared
separately, because RELION writes a timestamp label at offset 224 (`src/rwMRC.h`). Per-movie STAR
compared byte-for-byte, which covers the `data_hot_pixels` block in push order. Movie log compared
excluding lines carrying timing values.

| # | Cell | Pixels | STAR | Log | Hot pixels base / cand | Guards fired |
|---|---|---|---|---|---|---|
| T1 | gain, `--j 8`, GPU 0 | identical | identical | identical | 67 / 67 | 0 |
| T2 | no gain | identical | identical | identical | 237 / 237 | 0 |
| T3 | defect file + gain | identical | identical | identical | 67 / 67 | 0 |
| T4 | defect file, no gain | identical | identical | identical | 237 / 237 | 0 |
| T5 | `--skip_defect` | identical | identical | identical | n/a | 0 |
| T6 | `--j 1` | identical | identical | identical | 67 / 67 | 0 |
| T8 | CPU path, no `--gpu` | identical | identical | identical | 67 / 67 | 0 |
| T10 | streaming `--bin_factor 2` (synthetic) | identical | identical | — | 0 / 0 | 0 |
| T12 | zero-hot-pixel synthetic | identical | identical | — | 0 / 0 | 0 |
| T7 | candidate determinism, rep1 vs rep2 | identical | — | — | — | — |

`--j 8` matched-case statistics, both arms:
`In unaligned sum, Mean = 22.9369 Std = 4.88806 Hotpixel threshold = 52.2653` / `Detected 67 hot pixels`.

The zero-hot-pixel synthetic reproduces the committed reference
(`test-data/fixtures/reference_output/synthetic_128x128_8frames.log`) exactly:
`Mean = 834.965 Std = 62.8917 Hotpixel threshold = 1212.32` / `Detected 0 hot pixels`.

`--bin_factor 2` on the tutorial movie fails on **both** arms with
"The dimensions of the image after binning must be even" (3710/2 and 3838/2 are both odd). That is
a pre-existing input constraint, not a regression; the streaming path was exercised on the
synthetic fixture instead.

Builds: `-DCUDA=ON` and `-DCUDA=OFF` both compile clean.

## 4. Transfer volumes — the headline result

Nsight Systems, `nsys stats --report cuda_gpu_mem_size_sum`, matched single-movie runs:

| Operation | Baseline `a11f2f1` | Candidate | Delta |
|---|---|---|---|
| Device-to-Host | **113.915 MB** | **56.960 MB** | **-56.955 MB (-50.0%)** |
| Host-to-Device | 1,434.797 MB | 1,434.797 MB | 0 |
| Device-to-Device | 2,735.358 MB | 2,735.358 MB | 0 |

The 56.955 MB drop matches the initial-sum image exactly. D2H count falls from 106 to 109
operations totalling half the bytes — the large 56.956 MB transfer is gone, replaced by a few
hundred bytes of index list. Transfer volume is immune to host contention, so this result does not
depend on box quiescence.

**Re-confirmed on the post-audit-fix binary** (sha256 `15febf55fd685f98d7cbd9b20aa23bb8c2d775e8552534a031dea48ad73daad8`,
the same binary used for every result in §6-§10), on a settled box (load 1.82, zero GPU processes):

| Operation | Fixed candidate |
|---|---|
| Device-to-Host | **56.960 MB** |
| Host-to-Device | 1,434.797 MB |
| Device-to-Device | 2,735.358 MB |

Identical to the pre-fix figures. The rigorous-bound fix added `sum|x|` to the reduction, which
costs 8 additional bytes of D2H and does not change transfer structure — confirmed rather than
assumed.

## 5. Provenance (final series, 2026-09-24T19:37:54Z-19:44:13Z, one flock acquisition)

Host `4GPUs` / 4-gpu-vm, A100 80GB PCIe, driver 570.86.10, GPU 0.

> **Provenance caveat — these measurements predate the shared-VM CPU cap.** Every run in this
> report was taken with the full host CPU pool available (~124 logical CPUs), before `4GPUs` was
> capped to 8 logical CPUs (`taskset -c 96-103`, build parallelism <= 8, one job at a time).
> **Absolute wall times here are therefore not comparable to anything measured under the cap**, and
> should not be diffed against post-cap numbers.
>
> Two things are unaffected. The **exactness results are invariant**: `--j` fixes the OpenMP team
> size via `num_threads(n_threads)` regardless of how many cores exist, so the reduction order, the
> hot-pixel set and every corrected pixel are unchanged by the cap. The **paired wall-clock
> comparison also stands**, because both arms ran interleaved under identical conditions — the cap
> shifts both arms together and cannot manufacture a 34/40 sign split. Only the absolute figures
> (2.2292 s / 2.1876 s) are tied to the pre-cap configuration.
>
> Transfer volumes, stage timings relative to each other, and VRAM peaks are likewise comparisons
> internal to a matched pair and are not invalidated.
Box settled before any measured run: compilers 0, GPU processes 0, load1 1.97, waited 70 s.

| Tree | Binary | sha256 |
|---|---|---|
| base `a11f2f1` | `build-cuda/motioncorr` | `fdee080dd1314854c9c93f12c9ddd4f09f85bf34e020718f6547215c325497d9` |
| base `a11f2f1` | `build-timing/motioncorr` | `1fc064903e47ac5dad2e682a7febd1c21bd1c20742e579b821620706e27e51b7` |
| candidate | `build-cuda/motioncorr` | `15febf55fd685f98d7cbd9b20aa23bb8c2d775e8552534a031dea48ad73daad8` |
| candidate | `build-timing/motioncorr` | `b3e64d8e6c1a9d4387a1c0ef31270df7ebfb08e1b87705625d484bbb471f9b47` |
| probe (throwaway, **never merged**) | `build-cuda/motioncorr` | `7d5a759f7268087eb6f4913eb43aa600d977900e30cb400dd977a7e93222a37d` |

All trees identical flags:
`CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`
`CUDA_FLAGS = -O3 -DNDEBUG -std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80]`

Candidate source digests (sha256, first 16): `motioncorr_runner.cpp` `2908fc821ce0ecf6`,
`cuda_movie_session.cu` `9537a12246f035a9`, `cuda_movie_session.h` `f4696971603f1c42`.

The probe tree exists only to assert Guard 2 reachability. **Production is probe-free**: the
instrumentation is applied to a copied tree by `mkprobe.sh` and never enters the branch.

## 6. Guard 2 is reached, and proven to be reached

Ten green cells prove nothing about Guard 2 on their own: isolated hot pixels have `n_ok = 24`, so
`rnd_gaus` is never called and `frame_mean`/`frame_std` are unobservable. A clustered
border-adjacent defect file (`0 0 12 12`, `3698 3826 12 12`, `1000 0 1 14`) forces block-interior
pixels with every neighbour masked or out of bounds.

Reachability is **asserted, not inferred from geometry**, with both controls:

| Probe case | `gaus_reachable` | Expected |
|---|---|---|
| plain tutorial movie | **0** | 0 — isolated hot pixels |
| clustered border fixture | **1** | 1 — corner block gives `n_ok = 0` |

The negative control matters as much as the positive: had `plain` also reported 1, the probe
itself would be wrong. With Guard 2 genuinely exercised, the clustered-defect run is
**bit-identical** (pixels and STAR) to `a11f2f1`. The final integrated source uses
the original host scan for this case.

## 7. Cross-movie RNG parity — 24-movie sweep

`rnd_gaus` keeps a `static int call` Box-Muller pair cache that `init_random_generator` does not
reset, so one divergent draw in movie *k* desynchronises parity for every later movie. A
single-movie run is structurally incapable of detecting this.

All 24 tutorial movies, one process, `--j 8 --gpu 0`, gain + dose weighting:

- **24/24 per-movie corrected-pixel digests identical**, `differing_movies=0`
- hot-pixel counts identical in movie order: 67, 59, 70, 64, 59, 65, 60, 63, 73, 59, 58, 70, 57,
  62, 69, 74, 77, 61, 71, 63, 62, 59, 63, 70
- `corrected_micrographs.star` identical

## 8. Perturbation exactness

**Digest definition** (stated so a reviewer with the wrong tool does not conclude fabrication):
every digest in this report is the **first 16 hex characters of the SHA-256** of the MRC pixel
payload from byte 1025 onward, i.e. `tail -c +1025 <file> | sha256sum`. The 1024-byte header is
excluded because RELION writes a timestamp label at offset 224. For the matched case the full
SHA-256 is `09680a6a4b3914f97c5befbf87c53c2425ab06587801257c27d210c596eb7742`; the SHA-1 of the
same bytes is `41f04eb66b61d6e5aa3fb87f9fb474df4a5b2b77`, which will not match if checked with the
wrong algorithm.

A quiet-box run does not probe ordering surface, and this change adds a reduction and an
`atomicAdd` compaction. Corrected-pixel digest under deliberately different timing profiles:

| Profile | Wall | Digest |
|---|---|---|
| quiet (control) | 2.050 s | `09680a6a4b3914f9` |
| `CUDA_LAUNCH_BLOCKING=1` | 2.246 s | `09680a6a4b3914f9` |
| contended (competing GPU load) | 3.397 s | `09680a6a4b3914f9` |
| `a11f2f1` baseline reference | — | `09680a6a4b3914f9` |

The contended profile is **1.66x slower**, so the perturbation demonstrably took effect — a
profile that failed to perturb would look identical to a passing one.

### Independent cross-check

A separate task's candidate — removing 47 host barriers from the FFT loops, a completely different
change — produces the **same** corrected-pixel digest `09680a6a4b3914f9` as this change and as
`a11f2f1`, across their four timing profiles and these three. Two independent modifications landing
on identical pixels against the shared baseline is stronger evidence than either series alone, and
is a partial (not sufficient) signal for the combined commit. The merge still needs measuring in
its own right, particularly for VRAM, where deltas must not be added.

## 9. Stage timing — the change does what it claims, at stage level

`TIMING=ON` builds, 3 repeats each after a discarded warm-up, interleaved, quiet box:

| Stage | Base median | Candidate median | Delta | Significance |
|---|---|---|---|---|
| **detect hot pixels** | 48.2 ms (sd 0.6) | **37.8 ms** (sd 3.4) | **-10.4 ms (-21.6%)** | **6.25 sigma — resolved** |
| fix defects | 55.3 ms (sd 1.0) | 50.6 ms (sd 1.3) | -4.7 ms (-8.5%) | 5.04 sigma — resolved |
| apply gain and initial sum | 178.3 ms | 174.6 ms | -3.6 ms | 0.37 sigma — within noise |

The `detect hot pixels` reduction is the target stage and the result is unambiguous. Notably the
audit's concern did **not** materialise: the added `gaus_reachable` scan over 14.2M `bBad` entries
and three `cudaMalloc`/`cudaFree` pairs per movie do not outweigh the removed reductions and scan.

`apply gain and initial sum` is unchanged, confirming that removing the D2H and replacing it with
an explicit `cudaDeviceSynchronize()` costs nothing — the wait was already there.

The `fix defects` improvement is **not claimed as an effect of this change**; it is most plausibly
a cache artefact, since the new `gaus_reachable` scan walks `bBad` immediately before that loop
re-walks it. Recorded for completeness, not attributed.

## 10. Process wall — resolved at n=40 paired, and it reverses the n=6 result

**An earlier n=6 unpaired series is superseded.** It showed process wall 2.1234 -> 2.1492 s, i.e.
the candidate apparently *slower* at 1.28 sigma, and this report previously recorded "no wall-clock
improvement". That conclusion was wrong, and it was wrong for a reason worth recording: at n=6 a
two-sided sign test has a floor of p = 0.031, reachable only if every pair agrees in sign, so n=6
cannot distinguish a moderate effect from noise **even in principle**. The n=6 candidate arm also
happened to carry a 2.258 s outlier that drove most of the apparent gap.

Re-run as **n=40 paired**, interleaved, with the arm order **alternating within each pair** so that
intra-pair drift and input page-cache warming cancel rather than systematically favouring whichever
arm runs second. Warm-up discarded. Settled box (load 0.86, waited 10 s), sole occupant.

| Metric | Base median | Candidate median | Paired median delta | Sign test | t |
|---|---|---|---|---|---|
| **Process wall** | 2.2292 s | **2.1876 s** | **+45.9 ms faster (2.06%)** | **34 pos / 6 neg, p = 1e-5** | +6.62 |
| **Full movie wall** | 1.3630 s | **1.3170 s** | **+44.0 ms faster (3.23%)** | **36 pos / 4 neg, p < 1e-5** | +7.26 |

Mean paired delta +46.1 ms (sd 44.1, SE 7.0) and +47.9 ms (sd 41.7, SE 6.6). **Both resolved.**

### Positional bias, measured rather than assumed

Because the arm order alternates, the 40 pairs split into two balanced sub-series that can be
solved for the true effect `E` and the positional bias `P` (the advantage accruing to whichever arm
runs second, e.g. from input page-cache warming):

| Sub-series | n | Mean delta | Pairs favouring candidate |
|---|---|---|---|
| base first (candidate runs 2nd) | 20 | +48.7 ms | 18/20 |
| candidate first (base runs 2nd) | 20 | +43.6 ms | 16/20 |

Solving `observed = E +/- P`: **E = +46.1 ms, P = +2.5 ms** to whichever arm runs second (full movie
wall: E = +47.9 ms, P = +3.1 ms). Two things follow.

First, **the effect reproduces independently under both orderings** — it is not a positional
artefact, because reversing the order does not reverse the sign or materially change the
magnitude. That is an internal replication, not just a cancellation.

Second, positional bias in *this* measurement is small (~2.5 ms). A parallel task measuring host
I/O stages found a much larger P of ~20 ms on the same host, which is consistent: their change
concerns TIFF read and MRC write, where page-cache warming between paired runs matters far more
than it does here. The lesson is that P is workload-specific and should be measured, not assumed
negligible — at 20 ms it would have been a material fraction of a 46 ms effect.

**One honest caveat on magnitude.** The measured ~46 ms exceeds the sum of the stage deltas in §9
(detect -10.4, fix defects -4.7, gain+sum -3.6, about -19 ms). The stage figures come from
`TIMING=ON` builds and the wall figures from Release builds, so they are not the same binary, and
the stage timers do not cover everything the change removes -- notably, not writing 54.32 MiB into
host memory avoids that cache eviction and the associated host-side bandwidth, which shows up in
wall time but in no stage counter. I am reporting the measured number and flagging that it is not
fully accounted for by the stage decomposition, rather than constructing an explanation for the
gap.

### Re-measured under the 8-CPU cap — the effect attenuates by ~63%

After `4GPUs` was capped to 8 logical CPUs (`taskset -c 96-103`, one job at a time), the paired
series was re-run inside the shared `capped.sh` wrapper. The cap was verified from *inside* the
run rather than assumed: the artifact records `nproc=8`, affinity `96-103`.

| | Uncapped (~124 CPUs), n=40 | Capped (8 CPUs), n=30 |
|---|---|---|
| base median | 2.2292 s | 2.0872 s |
| candidate median | 2.1876 s | 2.0710 s |
| **paired median delta** | **+45.9 ms (2.06%)** | **+17.8 ms (0.85%)** |
| mean delta | +46.1 ms (SE 7.0) | +17.1 ms (SE 7.9) |
| sign test | 34/40 pos, p = 1e-5, t = 6.62 | 21/30 pos, p = 0.043, t = 2.15 |
| full movie wall delta | +44.0 ms, 36/40, t = 7.26 | +15.0 ms, 22/30, p = 0.008, t = 2.42 |
| positional bias P | +2.5 ms | +4.4 ms |

Corrected-pixel digest under the cap is `09680a6a4b3914f9` on **both** arms — identical to the
uncapped baseline, so bit-exactness is confirmed in the new configuration rather than inherited.

**The effect survives but is roughly a third of its uncapped size, and I predicted the wrong
direction.** My prior reasoning was that this change *offloads* host work to the GPU, so scarcer
CPUs should make it matter more. That was wrong: it matters less. The measurement was run because
a parallel task demonstrated that a cap-sensitivity argument one has not actually run is worth
little, and that judgement was correct.

An observation worth flagging rather than explaining: **the baseline itself got 142 ms faster under
the cap** (2.2292 -> 2.0872 s). Pinning to 8 adjacent logical CPUs plausibly improves locality and
removes thread migration and NUMA-crossing cost that an unpinned 124-core box incurs, and some of
the uncapped 46 ms may have been the candidate recovering overhead that the cap removes for both
arms. That is a hypothesis consistent with the numbers, not a measured mechanism.

**The attenuation is tested, not just a point-estimate comparison.** Comparing two medians and
declaring a difference would be the same error as reading significance off an underpowered series.
A two-sided permutation test (200,000 relabellings) on the two delta *sets*:

| Metric | Uncapped mean | Capped mean | Regime difference | Welch t | Permutation p |
|---|---|---|---|---|---|
| process wall | +46.1 ms (n=40) | +17.1 ms (n=30) | +29.1 ms | +2.76 | **0.0077** |
| full movie wall | +47.9 ms (n=40) | +17.8 ms (n=30) | +30.0 ms | +3.04 | **0.0037** |

So the regimes genuinely differ and the attenuation is established, not inferred from point
estimates. (A parallel task ran the same test on their own result and got p = 0.080 — their
regime difference is *undetermined* between shifted and attenuated. Same test, different
outcome; worth noting that the classification has to be earned per result.)

**Classification.** A parallel task proposed separating results that are *shifted* by the cap from
those *eliminated* by it. This one is neither — it is **attenuated**: still resolved, still
positive, still favoured under both orderings, but a third of the size. The binary needs a third
bucket, and any summary should quote the constrained figure when the deployment is constrained.

### The page-fault explanation for the residual is wrong, by inspection and by measurement

I had offered the avoided 54.32 MiB host write as the likely cause of the gap between the measured
~46 ms and the ~19 ms the stage decomposition accounts for. **That explanation is wrong, and it is
wrong for a reason visible in the source.**

`motioncorr_runner.cpp:1288-1289` is unchanged by this work:

```cpp
MultidimArray<float> Isum(ny, nx);
Isum.initZeros();
```

`initZeros()` writes the whole array, so **all 13,900 pages are faulted in on both arms** before
the preprocessing stage is reached. The baseline's D2H then rewrites pages that are already
resident. This change removes the *write*, not the *faulting*. There was never a page-fault saving
to find.

Measured under the cap (`/usr/bin/time -v`, 5 repeats each after a warm-up, medians):

| Counter | Base | Candidate | Delta | Expected if the buffer were avoided |
|---|---|---|---|---|
| Minor page faults | 450,446 | 459,682 | +9,236 (base spread 58,474) | **-13,900** |
| Involuntary context switches | 41 | 40 | -1 | — |
| Max RSS | 1,634,100 KiB | 1,633,692 KiB | -408 KiB | -55,603 KiB |

No fault saving, and no RSS saving either — consistent with `initZeros` dirtying the pages
regardless, and with the host `Isum` allocation being retained.

**The distinction from a parallel task's ~47 MB RSS drop is structural, not a discrepancy between
measurements.** `askMemory` is `calloc` (`src/memory.cpp:30`), and at 54.3 MiB the allocation is
well above any mmap threshold, so it returns **lazily-faulted** zero pages. Whether a saving exists
therefore depends on *whether the pages are ever touched at all*:

- Their change removes a staging buffer outright — allocation and write both disappear, so the
  faults genuinely never occur: −18,345 faults, −47 MB RSS.
- This change removes only a *write* to pages that `initZeros()` has already faulted in. No fault
  saving is possible, by construction.

A reader comparing −47 MB against −408 KiB should read that as two different mechanisms, not two
disagreeing measurements.

**So my unexplained residual stays open, with one candidate eliminated rather than confirmed.**
Avoided memory bandwidth for the 54.32 MiB write is still plausible and still unmeasured.

On the locality hypothesis for the 142 ms baseline shift under the cap: involuntary context
switches are **~40 per run**, far too few to account for tens of milliseconds, matching a parallel
task's independent finding (75 uncapped vs 70 capped on their workload). That weakens the migration
explanation substantially. I cannot test my own *uncapped* counters directly, because doing so now
requires an uncapped run and the shared-VM policy forbids one. Recorded as unresolved rather than
quietly retained.

## 10b. VRAM

| Metric | Base | Candidate |
|---|---|---|
| Peak whole-device VRAM (50 ms NVML) | 3533 MiB | 3533 MiB |

Identical on both arms, which is the comparison that matters here: the 1.51 MiB hit buffer is RAII
scratch freed before the alignment/reconstruction stage where the peak occurs, so it is invisible
as designed.

**Do not derive dataset headroom from the 3533 MiB figure.** A parallel task measured the same
baseline commit on the same movie with a 5 ms sampler (~740 samples/run, n=6, sd 0.000) and got
**3537 MiB**. The 4 MiB gap is not a difference between arms -- it is a coarse-sampler under-read,
my 50 ms sampler taking only ~67 samples per run and stepping between allocation events. Same
failure mode, at small scale, as the 6,636 MiB traced peak versus 6,033 MiB NVML sample in the
addendum. The figure to quote is **47 MiB of headroom (1.31%)** against the 3,584 MiB ceiling, and
even that is an *upper* bound, since every sampled peak is a lower bound on the true peak. The
ceiling should not be described as comfortably met.

## 10c. CPU-only reference on `cpu64` (off the GPU host)

Per the revised host allocation, CPU-only reference work was moved off `4GPUs` entirely. Source was
staged by `git archive <sha> | ssh cpu64 tar -x` for both arms — `a11f2f1` and the candidate — so
the trees are exact, and the synthetic fixtures travel with the branch. (`cpu64`'s existing
`relion-doppio-browser-project/MotionCorr` is a RELION job output directory, **not** a git
checkout, and must not be used as one.)

Host: `small-refmac-machine`, 64 cores, 226 GB, gcc 13.3.0. Built `-DCUDA=OFF
-DCMAKE_BUILD_TYPE=Release` with the user-local venv cmake (`~/.mc-venv/bin/cmake`; the host has no
system cmake), `nice`, `-j16` of 64 on a shared machine. Both arms built clean.

| Fixture | `--j` | Pixels | Header 0-223 | STAR | Digest |
|---|---|---|---|---|---|
| `synthetic_128x128_8frames` | 1 | identical | identical | identical | `8affd8ecb171af22` |
| `synthetic_128x128_8frames` | 8 | identical | identical | identical | `8affd8ecb171af22` |
| `synthetic_128x128_8frames_subpixel` | 1 | identical | identical | identical | `a8b6cb95bb9b8e2d` |
| `synthetic_128x128_8frames_subpixel` | 8 | identical | identical | identical | `a8b6cb95bb9b8e2d` |

This is a genuinely independent check: different host, different CPU vendor, different gcc, no CUDA
in the binary at all. It confirms the change is inert on the pure-CPU path — which it must be,
since every new code path is behind `#ifdef _CUDA_ENABLED` and a live `movie_session`.

## 11. Gate 2

**Unchanged.** This change is output-neutral — corrected pixels, shifts and metadata are
bit-identical to `a11f2f1` in every cell tested. It therefore neither improves nor worsens the
pre-existing relative-RMSE failure, and no tolerance was altered, overridden or reinterpreted. A
separate session has since traced that failure to sub-pixel peak interpolation in the
global-alignment CCF, which is outside this change's scope.

## 12. Fault-injection: the fallback is exercised and exact

A throwaway build (`~/MotionCorr-hotpixel-fault`, separate binary, never merged) forces
`collectAboveThreshold` to return false on every call. Matched T1 configuration:

```
FAULTINJ: forcing collectAboveThreshold failure
In unaligned sum, Mean = 22.9369 Std = 4.88806 Hotpixel threshold = 52.2653
Detected 67 hot pixels to be corrected.
```

Exit status 0, corrected pixels **bit-identical to the `a11f2f1` baseline**, per-movie STAR
identical. So the guard path downloads the resident sum, re-runs the original host scan verbatim,
and produces the reference result with the session still alive — confirming the design decision
not to call `movie_session.reset()` on a statistics failure.

## 13. Known gaps and adjacent findings

- **EER not exercised**; no `.eer` fixture exists in the repo. The only EER coupling is
  `D_MAX = 4` in the replacement loop, which this change does not touch.
- **`--bin_factor 2` on the tutorial movie fails on both arms** ("dimensions after binning must be
  even"; 3710/2 and 3838/2 are both odd). Pre-existing input constraint, not a regression; the
  streaming path was covered on the synthetic fixture instead.
- **Gate 2 relative-RMSE remains failing**, unchanged and untouched by this work. A separate
  investigation traced it to sub-pixel peak interpolation in the global-alignment CCF, with the
  forced-common-trajectory control dropping relative RMSE from 0.004708 to 0.000345.
- **Adjacent finding, deliberately not implemented**: `Igain` is local to
  `executeOwnMotionCorrection` (`:1164`) and re-read per movie (`:1258`), so a 24-movie run pays
  the same MRC read 24 times (~2.5 s). Verified it is only ever read (`:1304`, `:1348`,
  `:1477-1479`, `:1612`), so caching is safe. **Left out of this change on purpose**: folding it in
  would make a moved digest in the 24-movie RNG sweep unattributable. A correct fix needs a cache
  keyed on (filename, nx, ny, EER-or-not) rather than an unconditional hoist, because the
  per-movie size check at `:1260-1262` exists for non-uniform STAR files and the EER path takes a
  different branch (`renderer.loadEERGain`, `:1256`). Credited to the non-kernel wall-time task.
- The timings above belong to the original measured branch. The integrated final-head
  comparison, including signed summed pixels and clustered defects, is below.

## 14. Final integrated head (`bb53e04`)

The exact PR #54 head was built clean on `4GPUs` as Release, CUDA `sm_80`, with
`CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`. The production binary SHA-256 is
`5f5651d37d6ce8d8425dd034082767acd92c5b4f2475654889ea62165450f5c9`; the
`a11f2f1` reference binary SHA-256 is
`fdee080dd1314854c9c93f12c9ddd4f09f85bf34e020718f6547215c325497d9`.
The validation ran under `flock /tmp/motioncorr-bench.lock` and top-level
`taskset -c 96-103`, with build parallelism 8. The unedited console record,
including flags, hashes, GPU identity, and raw results, is committed as
`agents/reports/issue_50_hotpixel_final_head_validation.txt`. The command script
and separate provenance file remain at `/tmp/hp54c/validate54c.sh` and
`/tmp/hp54c/PROVENANCE.txt` on that host.

The instrumented reachability controls reported Gaussian fallback **unreachable**
for normal and signed plain gain, and **reachable** for normal and signed clustered
defects. The latter two used the original host statistics. All five single-movie
controls (`gain_plain`, `gain_clustered`, `signed_plain`, `signed_clustered`,
`nogain_plain`) matched the reference in corrected pixels, the first 224 header
bytes, STAR files, and ordered hot-pixel lists. The full tutorial run produced
24/24 corrected movies with identical pixel digests, 0 ordered hot-pixel-list
differences, identical per-movie hot-pixel counts, and an identical dataset STAR.

In 12 alternating paired process-wall runs under the 8-core cap, the reference
median was **2.331 s** and this head's median **2.343 s**; the median paired
advantage was only **8.3 ms**, with this head faster in 6/12 pairs. This does
**not** resolve an end-to-end speedup. The earlier 17.8 ms/0.85% result and
21.6% detection-stage improvement are measurements of the earlier branch, not
claims for `bb53e04`. The structural device-to-host transfer reduction on that
branch was 113.915 to 56.960 MB. The final-head run did not remeasure transfer
bytes. A 50 ms NVML sampler saw up to **3537 MiB** in each arm, leaving at most
47 MiB below the 3584 MiB ceiling; sampling can miss the true peak.

**Verdict:** The exact final head passes the tested output-equivalence gates and
is suitable for the stacked PR #54 merge into #51. Its end-to-end performance
gain is unresolved under the shared-host cap. EER, CPU/RELION Gate 2, the
low-memory fallback, and the tight memory-headroom decision remain open on #51.
