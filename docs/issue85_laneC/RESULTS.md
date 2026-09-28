# Issue #85 lane C — measured results

Native uint16 TIFF host staging with device-side conversion and gain. Design:
`agents/designs/issue_85_lane_c_uint16_staging.md`. Raw per-arm records are the `*.run.txt` files in
this directory; `series.log` is the interleaved timing series; `compare_gain.txt` /
`compare_nogain.txt` are the full comparator outputs.

## Provenance

| | |
|---|---|
| base (control) | main `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38`, binary sha256 `614c0090…99374` |
| candidate | `05313811284c1c25825f3421eee8fe5fe0ef3817`, binary sha256 `ee631181…41c6` |
| build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80`, `-O3 -DNDEBUG`, no fast math, no FP flags |
| toolchain | g++ 13.3.0, nvcc 12.8.61, cmake 3.28.3, driver 570.86.10 |
| host | `4-gpu-vm`, AMD EPYC 7452, `taskset -c 96-103` (8 physical cores, NUMA node 1), `OMP_NUM_THREADS=8` |
| GPU | A100 80GB PCIe `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, selected by UUID |
| input | 24 RELION SPA tutorial movies, 3710x3838x24 uint16 Adobe-Deflate TIFF, RowsPerStrip=1; concatenated sha256 `6d84d0ed…3b98`; gain sha256 `8919cdc7…acd1` |
| options | `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --gpu 0 --j 8` (+ `--gainref Movies/gain.mrc` on the gain arms) |

Payload arithmetic, parsed directly from the IFDs: 341,735,520 px/movie; uint16 683,471,040 B
(0.6365 GiB); float32 1,366,942,080 B (1.2731 GiB).

## 1. Products — byte-identical

`compare_output_trees.py` compares MRC pixel payloads and the first 224 header bytes exactly,
reports the 224–1024 label block separately (it carries a creation timestamp), and runs its own
negative control afterwards.

| comparison | files | MRC images | pixels | differing | negative control |
|---|---|---|---|---|---|
| base vs candidate, **with gain** | 105 | 24 | 341,735,520 | 24, **all `.log`** | tripped (2 extra) |
| base vs candidate, **no gain** | 105 | 24 | 341,735,520 | 24, **all `.log`** | tripped (2 extra) |
| base vs base rerun | 105 | 24 | 341,735,520 | **0** | tripped (2) |
| candidate vs candidate rerun | 105 | 24 | 341,735,520 | **0** | tripped (2) |

All 24 corrected MRCs and all 25 STAR files are byte-identical in both arms. The 24 differing files
are the per-movie `.log`s, and the difference is the one diagnostic line the candidate adds
(`Staging this movie as native unsigned 16-bit…`). The same-arm reruns are clean, which is what
establishes that those 24 diffs come from the binary and not from run-to-run variation.

The no-gain arm matters: it is the only configuration that exercises the case where the reference
kernel never writes `d_Iframes`. It is a stress control, not a product mode — without a gain the
alignment differs, so it is compared only against its own baseline, never against the gain arm.

### Device-level equivalence

`CudaU16StagingEquivalence` (new, CTest label `cuda;hardware`) builds both arms on a 61x47x5 movie
and compares the unaligned sum **and all resident frames** as raw bytes:

```
PASS no gain: sum and all 5 resident frames are byte-identical
PASS plain gain: sum and all 5 resident frames are byte-identical
PASS hostile gain: sum and all 5 resident frames are byte-identical
PASS negative control: one-count change detected (unaligned sum differs)
PASS frame-oracle control: changed resident frame detected (resident frame 4 differs)
```

"Hostile gain" contains zero, negative (`-1.5f`, so a zero sample gives `-0.0f`) and near-denormal
(`1e-30f`) entries. There are two negative controls because the comparison has two oracles and the
sum check short-circuits: one perturbs a uint16 sample, the other perturbs a downloaded frame.

### Instruction-level

`cuobjdump -sass` on the built objects. The baseline `fusedGainAndSumKernel` is **FFMA 0 / FMUL 30 /
FADD 59** and is byte-for-byte unchanged by the patch. The new kernel is
`LDG.E.U16 → I2F.U16 → @P0 FMUL → STG.E → LDG.E → FADD → STG.E`, **FFMA 0** — no contraction, so the
product is rounded once exactly as the reference rounds it.

## 2. Host memory — −0.637 GiB

Peak RSS, `/usr/bin/time -v` (agrees with a 200 ms `/proc/<pid>/status` `VmHWM` sampler), gain arm,
three runs each from the interleaved series:

| arm | run 1 | run 2 | run 3 | mean |
|---|---:|---:|---:|---:|
| base | 1,596,240 kB | 1,595,848 kB | 1,596,148 kB | **1,596,079 kB** (1.522 GiB) |
| candidate | 926,904 kB | 928,392 kB | 928,184 kB | **927,827 kB** (0.885 GiB) |

**Δ = −668,252 kB = −0.637 GiB = −41.9%.** The predicted movie delta is 667,452 kB; measured and
predicted agree to 0.12%, so the saving is the movie representation and nothing else.

Within-arm spread is 392 kB (base) and 1,488 kB (candidate) — four orders of magnitude below the
difference.

### Degraded path

A patch that does not converge downloads the full float movie from the device. In the no-gain stress
arm that happens, and it is where the first two versions of this change regressed:

| version | no-gain peak RSS |
|---|---:|
| main | 1,587,308 kB (1.51 GiB) |
| staging held to end of movie | 2,258,340 kB (2.15 GiB) — **worse than main** |
| staging dropped after the forward FFT | 2,063,576 kB (1.97 GiB) — still worse |
| + `malloc_trim(0)` on drop | **1,572,812 kB (1.50 GiB)** — below main |

Both steps were necessary. Freeing without trimming left the arena holding the 0.637 GiB, so the
download stacked on top of it.

## 3. PCIe — −683.47 MB per movie

`nsys profile --trace=cuda --cuda-memory-usage=true`, single movie, both arms back to back:

| | base | candidate | Δ |
|---|---:|---:|---:|
| H2D bytes | 1,434.807 MB | 751.336 MB | **−683.471 MB (−47.6%)** |
| H2D count | 270 | 270 | 0 |
| H2D device time | 223.57 ms | 97.18 ms | −126.4 ms |
| D2H bytes | 56.966 MB | 56.966 MB | 0 |
| memset bytes | 57.011 MB | 113.967 MB | +56.956 MB (the `d_Isum` zeroing) |
| gain/sum kernel | 2.845 ms (1 launch) | 3.877 ms (24 launches) | **+1.03 ms** |

The byte reduction is exactly 683,471,040 B, the uint16-vs-float32 movie delta. The kernel pays
1.0 ms for a 126 ms transfer saving on the device timeline.

## 4. Device memory — unchanged

Peak `memory.used` on the target GPU, sampled at 200 ms and filtered to its UUID: **3,493 MiB in all
four arms** (base/candidate x gain/no-gain). nsys traced allocations are identical between arms
except for one transient 28,477,960 B (27.16 MiB) alloc/free pair — the per-frame staging buffer,
live only inside `applyGainDefectsAndSumU16`.

## 5. Wall time — −20.7%

Interleaved `base, cand, cand, base, base, cand`, 24 movies, gain arm, one GPU (`series.log`):

| arm | runs (s) | mean | spread |
|---|---|---:|---:|
| base | 32.813, 31.134, 30.758 | **31.568 s** | 2.055 s |
| candidate | 25.703, 24.680, 24.747 | **25.044 s** | 1.023 s |

**Δ = −6.52 s (−20.7%).** The arms do not overlap: the slowest candidate run is 5.1 s faster than
the fastest base run.

**Limitation.** Box-wide exclusivity was not available — other users held ~214% foreign CPU and two
compute apps on GPUs 0 and 1 throughout. The target GPU was exclusive (enforced by a UUID preflight),
foreign load was recorded per arm and was flat across all six, and the arm order alternated so drift
hits both. This supports "faster under these conditions by a margin far exceeding within-arm
spread"; it is not a clean-room speedup figure.

The device timeline accounts for ~126 ms/movie ≈ 3.0 s over 24 movies, about half the 6.5 s. The rest
is host-side: the baseline's per-element widening writes 1.273 GiB per movie where the candidate
`memcpy`s 0.637 GiB, with the matching reduction in first-touch page faults. That attribution is
inferred from the two measured components, not separately measured.

## 6. Test suites

| suite | result |
|---|---|
| CPU-only build, cpu64, `ctest` | **18/18 passed** (includes PR111's `GlobalIfftElision` and `CiFailClosedControls`) |
| CUDA build, 4GPUs, `ctest` | **20/20 passed** (adds `CudaU16StagingEquivalence`, `CudaWrapperUploadFailure`) |

`CudaU16StagingEquivalence` is registered as additive rather than in
`DEFAULT_REQUIRED_TESTS`, matching how `CudaWrapperUploadFailure` is treated: it is only collected
when `CUDA=ON` on Linux, so requiring it would fail CPU-only CI.

## 7. What this does not establish

- One geometry, one codec, one GPU, one worker. No multi-GPU throughput measurement.
- The wall-time figure comes from a shared box (see the limitation above).
- H2D bytes were measured on a single movie and multiplied by nothing — the 24-movie claim is the
  per-movie figure, stated per movie.
- The host-side share of the 6.5 s is inferred from the measured device delta, not measured directly.
- MRC mode 6 would take the same path with a one-line predicate change; untested, so excluded.
- EER, compressed MRC, packed 4-bit, signed 16-bit, 8-bit and float TIFF all keep the existing float
  path by construction; they were not re-measured, and the CPU suite covers their behaviour.
