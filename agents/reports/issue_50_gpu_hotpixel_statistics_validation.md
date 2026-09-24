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

## 5. Wall time and VRAM

**First batch discarded.** My `TIMING=ON` per-stage runs at ~19:05-19:07Z executed inside another
session's measurement window: the advisory lockfile `/tmp/motioncorr-gpu-timing.lock` was
overwritten (plain `>` has no test-and-set, so last writer wins), and at sample time `nvidia-smi`
showed a foreign process holding 3,364 MiB with load average 22.78. The contamination is visible
in the data — candidate `apply gain and initial sum` came out 0.394 / 0.508 / 0.719 s against a
tight baseline 0.364 / 0.390 / 0.392 s. Removing a 54 MiB copy cannot make a stage slower, so that
spread is contention. Those numbers are not reported.

**Wall/VRAM batch (n=6 per arm, interleaved, warm-up discarded, GPU 0, `-O3`)** — collected before
the collision but not in a verified-quiet window, so reported as provisional:

| Metric | Baseline | Candidate | Delta |
|---|---|---|---|
| Process wall, median | 2.2575 s (sd 0.083) | 2.2179 s (sd 0.105) | +0.0396 s |
| Full movie wall, median | 1.4210 s (sd 0.111) | 1.4085 s (sd 0.081) | +0.0125 s |
| Peak whole-device VRAM (50 ms NVML) | 3537 MiB | 3533 MiB | -4 MiB |

**The wall-time difference is within noise and is not claimed as a win.** The standard error of
the mean difference is 0.055 s, larger than either delta. This is consistent with the ~4% process
noise three sessions have independently measured on this host. A change of this size (tens of ms
against a ~2.2 s process) is not resolvable at n=6, and probably not at any practical n without
stage-level instrumentation in a verified-quiet window.

VRAM stays under the 3,584 MiB ceiling on both arms. The hit buffer is 1.51 MiB of RAII scratch
freed before the alignment/reconstruction stage where the peak occurs, so no increase is expected;
the -4 MiB is sampling luck, not a saving.

## 6. Honest assessment of the payoff

The transfer reduction is real, exactly as predicted, and permanent: **D2H halves.** On a
PCIe-constrained or multi-GPU-per-host configuration that is worth having, and it removes the last
structural reason the sum had to be materialised on the host.

The wall-clock benefit is **not demonstrated**. The removable host work measures ~20 ms at `--j 8`
in a standalone harness, and the 54.32 MiB copy is roughly 7-20 ms — together order 1% of process
wall, well under the measurement noise floor. Anyone quoting "0.186 s of host scan removed" as the
benefit of this change would be wrong twice over: that figure covers the whole
`TIMING_DETECT_HOT` stage including the `bBad` allocation, `fillDefectMask` and the serial
gain-zero scan, of which this change removes only part; and it appears to derive from an
unoptimized build (`CMakeLists.txt` sets no default `CMAKE_BUILD_TYPE`, so an unqualified
configure yields `-O0`).

## 7. Gate 2

**Unchanged.** This change is output-neutral — corrected pixels, shifts and metadata are
bit-identical to `a11f2f1` in every cell tested. It therefore neither improves nor worsens the
pre-existing relative-RMSE failure, and no tolerance was altered, overridden or reinterpreted. A
separate session has since traced that failure to sub-pixel peak interpolation in the
global-alignment CCF, which is outside this change's scope.

## 8. Fault-injection: the fallback is exercised and exact

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

## 9. Known gaps

- Wall/VRAM numbers are provisional pending a verified-quiet re-run. The box has been continuously
  contended by four other sessions; the contention-immune evidence (§4) is unaffected.
- The full 24-movie dataset run required by the addendum before calling this release-ready has not
  been performed.
- Not pushed to PR #51, per instruction.
- EER was not exercised; no `.eer` fixture exists in the repo. The only EER coupling is
  `D_MAX = 4` in the replacement loop, which this change does not touch.
