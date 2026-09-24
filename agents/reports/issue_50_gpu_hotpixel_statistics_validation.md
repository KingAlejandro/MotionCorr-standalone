# Issue #50 / PR #51 follow-on: GPU hot-pixel statistics — validation report

**Branch**: `t3code/gpu-hot-pixel-optimization`
**Commit**: `a5a4816`
**Baseline**: `a11f2f1` (`origin/feat/issue-50-cuda-end-to-end-residency`)
**Design**: `agents/designs/issue_50_gpu_hotpixel_statistics.md`
**Host**: `4GPUs` (4-gpu-vm), A100 80GB PCIe, GPU 0
**Builds**: both arms `cmake -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_BUILD_TYPE=Release`,
verified `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`

Not pushed to PR #51. No other worktree or branch was modified.

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
hundred bytes of index list. Transfer volume is immune to host contention, so this result is
robust to the measurement problems in §5.

## 5. Provenance (final series, 2026-09-24T19:37:54Z-19:44:13Z, one flock acquisition)

Host `4GPUs` / 4-gpu-vm, A100 80GB PCIe, driver 570.86.10, GPU 0.
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
**bit-identical** (pixels and STAR) to `a11f2f1`, with no guard warnings.

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

## 10. Process wall and VRAM — no improvement demonstrated

n=6 per arm, interleaved, warm-up discarded, Release builds, quiet box:

| Metric | Base median | Candidate median | Delta | Significance |
|---|---|---|---|---|
| Process wall | 2.1234 s (sd 0.026) | 2.1492 s (sd 0.053) | **-0.0257 s (candidate slower)** | 1.28 sigma — within noise |
| Full movie wall | 1.2575 s (sd 0.020) | 1.2885 s (sd 0.056) | -0.0310 s (candidate slower) | 1.41 sigma — within noise |
| Peak whole-device VRAM (50 ms NVML) | **3533 MiB** | **3533 MiB** | 0 | under the 3,584 ceiling |

**Whole-process wall time shows no improvement, and the point estimate leans the wrong way.**
Neither delta is statistically resolved, and the candidate arm carries one 2.258 s outlier that
drives most of the gap. The honest statement is that a ~15 ms stage-level gain is not observable
in a ~2.1 s process with ~25-50 ms run-to-run spread, and this measurement cannot distinguish a
small real gain from a small real loss.

Peak VRAM is identical at 3533 MiB on both arms. The 1.51 MiB hit buffer is RAII scratch freed
before the alignment/reconstruction stage where the peak occurs, so it is invisible as designed.
Note 47 MiB of headroom against 3,584 MiB is ~1.3%, inside what a 50 ms sampler can miss between
allocations; the ceiling should not be described as comfortably met.
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
- Not pushed to PR #51, per instruction. No other worktree or branch modified.

## 14. Verdict

**Functionally correct and safe to merge on the evidence gathered; the performance case is
stage-level only.**

What is established beyond reasonable doubt:
- Output is bit-identical to `a11f2f1` across ten single-movie configurations, a clustered-defect
  configuration that provably exercises Guard 2, all 24 tutorial movies in one process, and three
  deliberately perturbed timing profiles including one 1.66x slower.
- The fallback is real: forcing `collectAboveThreshold` to fail reproduces the reference
  bit-for-bit with the session still alive.
- Device-to-host transfer volume halves, 113.915 MB to 56.960 MB.
- `TIMING_DETECT_HOT` drops 21.6%, 48.2 to 37.8 ms, at 6.25 sigma.
- Peak VRAM unchanged at 3533 MiB, under the 3,584 MiB ceiling.

What is **not** established:
- Any whole-process wall-clock improvement. The point estimate leans slower and is not resolved.
  A ~15 ms stage gain is not observable against ~25-50 ms process spread.

The defensible headline is therefore **a halved D2H and a measurably faster detection stage, with
no demonstrated end-to-end speedup**. Anyone quoting this as "~0.19 s saved" or as a process-level
win would be overstating it.
