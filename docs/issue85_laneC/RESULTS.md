# Issue #85 lane C — measured results

Native uint16 TIFF host staging with device-side conversion and gain. Design:
`agents/designs/issue_85_lane_c_uint16_staging.md`. Raw per-arm records are the `*.run.txt` files
here; `series.log` is the interleaved timing series; `compare_*.txt` are full comparator outputs.

## Provenance

| | |
|---|---|
| base (control) | main `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38`, binary sha256 `614c0090…99374` |
| candidate | `05313811284c1c25825f3421eee8fe5fe0ef3817` (products/timings) — the later test-only commits do not touch `src/` |
| candidate binary | sha256 `ee631181…41c6` |
| build | `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80`, `-O3 -DNDEBUG`, no fast math, no FP flags |
| toolchain | g++ 13.3.0, nvcc 12.8.61, cmake 3.28.3, driver 570.86.10 |
| host | `4-gpu-vm`, AMD EPYC 7452, `taskset -c 96-103` (8 physical cores, NUMA node 1), `OMP_NUM_THREADS=8` |
| GPU | A100 80GB PCIe `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, selected by UUID |
| input | 24 RELION SPA tutorial movies, 3710x3838x24 uint16 Adobe-Deflate TIFF, RowsPerStrip=1; concatenated sha256 `6d84d0ed…3b98`; gain sha256 `8919cdc7…acd1` |
| options | `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --gpu 0 --j 8` (+ arm-specific flags) |
| comparator | `compare_output_trees.py` (retained here), sha256 `fa79a67daab581f5c9614893770160d46952dfbb162b5c5630969af45256da77`, invoked as `compare_output_trees.py <base>/out <cand>/out --expect-images 24` |
| log comparator | `compare_movie_logs.py` (retained here) |

Payload arithmetic, parsed directly from the IFDs: 341,735,520 px/movie; uint16 683,471,040 B
(0.6365 GiB); float32 1,366,942,080 B (1.2731 GiB).

## 1. Products

`compare_output_trees.py` compares MRC **pixel payloads and header bytes 0–224** exactly, reports the
224–1024 label block separately (it carries a creation timestamp that is never reproducible), and runs
its own negative control afterwards.

| comparison | files | MRC images | pixels | differing | negative control |
|---|---|---|---|---|---|
| base vs candidate, **gain** | 105 | 24 | 341,735,520 | 24, all `.log` | tripped (2 extra) |
| base vs candidate, **no gain** | 105 | 24 | 341,735,520 | 24, all `.log` | tripped (2 extra) |
| base vs candidate, **`--first_frame_sum 3 --last_frame_sum 20`** | 105 | 24 | 341,735,520 | 24, all `.log` | tripped (2 extra) |
| base vs candidate, **`--skip_defect`** | 105 | 24 | 341,735,520 | 24, all `.log` | tripped (2 extra) |
| base vs base rerun | 105 | 24 | 341,735,520 | **0** | tripped (2) |
| candidate vs candidate rerun | 105 | 24 | 341,735,520 | **0** | tripped (2) |

**In all four cross-arm comparisons every one of the 24 corrected MRCs matches exactly in pixel
payload and in header bytes 0–224, and all 25 STAR files match exactly.** The same-arm reruns are
clean, which is what establishes that the 24 `.log` diffs come from the binary and not from
run-to-run variation.

### What the 24 differing logs contain

Not only the added line. Size deltas are +116 B in the gain and frame-subset arms but 115/116/117 B
in the no-gain and skip_defect arms, so the added line (115 chars + newline = 116 B) is not the whole
story. Diffing shows the remainder is the GPU profile timing values — `cuFFT execution time: 1.66 ms`
vs `1.67 ms` and similar — whose digit count varies run to run.

`compare_movie_logs.py` establishes this for all 96 log pairs rather than by inspection: after
dropping the added line and every line carrying a duration or a VRAM figure, **0 of 24 logs differ in
each of the four arms**. So the hot-pixel mean/std/threshold, the "Detected N hot pixels" counts, the
per-iteration RMSD values and the shift tables are identical as well.

### Arms and what each is for

- **gain** — the product configuration.
- **no gain** — the only configuration that exercises the case where the reference kernel never writes
  `d_Iframes`. A stress control, compared only against its own baseline; without a gain the alignment
  differs, so it is not comparable to the gain arm.
- **frame subset** — 18 of 24 frames, so the staging vector is indexed by the dense index while
  `frames[]` holds file indices 2..19.
- **skip_defect** — the hot-pixel block, and with it the retargeted neighbour read, is skipped
  entirely and `materialize_host_frames` would run a gain-only pass.

### Device-level equivalence, and proof the test is not vacuous

`CudaU16StagingEquivalence` (new, CTest label `cuda;hardware`) runs both arms on a 61x47x5 movie and
compares the unaligned sum **and all resident frames** as raw bytes. Both arms poison `d_Iframes`
with `0xA5` before running, because the arms run back to back and `cudaMalloc` does not zero reused
memory — without the poison the uint16 arm's buffer is likely to come back holding the float arm's
just-freed contents, which are the expected answer.

```
fixture: 5 negative-zero products, 5 zero-gain pixels, 5 subnormal products
PASS no gain / plain gain / hostile gain: sum and all 5 resident frames byte-identical
PASS negative control: one-count change detected (unaligned sum differs)
PASS frame-oracle control: changed resident frame detected (resident frame 4 differs)
```

The fixture line is an assertion, not a print: the test fails if the hostile-gain arm does not
actually contain a zero sample under a negative gain entry, a zero gain entry and a subnormal
product. An earlier version of this fixture contained **none** of the negative-zero products it
claimed, so that arm proved nothing.

Two mutants were built and run to show the checks discriminate:

| mutant | what it changes | result |
|---|---|---|
| A | seed `d_Isum` with frame 0's product instead of `cudaMemset` | **caught** — `FAIL hostile gain: unaligned sum differs` |
| B | make the `d_Iframes` store conditional on `apply_gain`, as the float kernel has it | **caught** — `FAIL no gain: resident frame 0 differs` |

Mutant A survives the pre-fix fixture and mutant B survives without the poison, so both guards are
load-bearing.

### Instruction level

`cuobjdump -sass`. The baseline `fusedGainAndSumKernel` is **FFMA 0 / FMUL 30 / FADD 59** and is
unchanged by the patch. The new kernel is `LDG.E.U16 → I2F.U16 → @P0 FMUL → STG.E → LDG.E → FADD →
STG.E`, **FFMA 0** — no contraction, so the product is rounded once exactly as the reference rounds it.

## 2. Host memory — −0.637 GiB

Peak RSS, `/usr/bin/time -v` (agrees with a 200 ms `/proc/<pid>/status` `VmHWM` sampler), gain arm,
three runs each from the interleaved series:

| arm | run 1 | run 2 | run 3 | mean |
|---|---:|---:|---:|---:|
| base | 1,596,240 kB | 1,595,848 kB | 1,596,148 kB | **1,596,079 kB** (1.522 GiB) |
| candidate | 926,904 kB | 928,392 kB | 928,184 kB | **927,827 kB** (0.885 GiB) |

**Δ = −668,252 kB = −0.637 GiB = −41.9%.** The predicted movie delta is 667,452 kB; measured and
predicted agree to 0.12%, so the saving is the movie representation and nothing else. Within-arm
spread is 392 kB (base) and 1,488 kB (candidate).

This is a gain-arm figure. The no-gain arm is 1,587,308 → 1,572,812 kB (−0.9%), because in that arm
non-converging patches download the full float movie anyway; see below.

### Degraded path

A patch that does not converge downloads the full float movie from the device. That happens in the
no-gain arm, and it is where the first two versions of this change regressed:

| version | no-gain peak RSS |
|---|---:|
| main | 1,587,308 kB (1.51 GiB) |
| staging held to end of movie | 2,258,340 kB (2.15 GiB) — **worse than main** |
| staging dropped after the forward FFT | 2,063,576 kB (1.97 GiB) — still worse |
| + `malloc_trim(0)` on drop | **1,572,812 kB (1.50 GiB)** — below main |

Both steps were necessary. Freeing without trimming left the arena holding the 0.637 GiB, so the
download stacked on top of it.

## 3. PCIe — −683.47 MB per movie

`nsys profile --trace=cuda --cuda-memory-usage=true`, **one movie** (`20170629_00021`). Two pairs were
run, on the same inputs and the same runtime source, ~25 minutes apart. Both are reported: the byte
counts are identical between them, the times are not.

| | base | candidate | Δ |
|---|---:|---:|---:|
| **H2D bytes** (both runs) | 1,434,807,040 B (1434.807 MB) | 751,336,000 B (751.336 MB) | **−683,471,040 B (−47.6%)** |
| H2D count | 270 | 270 | 0 |
| H2D device time, run A | 144.38 ms (9.94 GB/s) | 69.00 ms (10.89 GB/s) | −75.4 ms |
| H2D device time, run B | 223.57 ms (6.42 GB/s) | 97.18 ms (7.73 GB/s) | −126.4 ms |
| D2H device time, run A | 19.95 ms | 7.02 ms | −12.9 ms |
| D2H device time, run B | 10.12 ms | 23.57 ms | **+13.4 ms** |
| D2H bytes | 56.966 MB | 56.966 MB | 0 |
| memset bytes | 57.011 MB | 113.967 MB | +56.956 MB (the `d_Isum` zeroing) |
| gain/sum kernel | 2.845 ms (1 launch) | 3.877 ms (24 launches) | **+1.03 ms** |

The **byte** reduction is exact and reproducible: 683,471,040 B, the uint16-vs-float32 movie delta,
identical in both runs. The **time** figures are not stable — the base arm alone spans 6.42–9.94 GB/s
on a byte-identical payload, and D2H reverses sign between runs, which no part of this change can
explain. Treat the H2D time saving as ~75–126 ms/movie (n=2 on a shared box), not as a point estimate.

The conversion kernel costs +1.0 ms/movie against that.

## 4. Device memory — unchanged

Peak `memory.used` on the target GPU, sampled at 200 ms and filtered to its UUID: **3,493 MiB in all
four arms** (base/candidate x gain/no-gain). This is a board-level figure at 200 ms granularity, so it
would not resolve a short-lived allocation; the allocation-level statement is stronger: nsys traced
allocations are identical between arms except for one transient 28,477,960 B (27.16 MiB) alloc/free
pair, the per-frame staging buffer, live only inside `applyGainDefectsAndSumU16`.

## 5. Wall time — −20.7%

Interleaved `base, cand, cand, base, base, cand`, 24 movies, gain arm, one GPU (`series.log`):

| arm | runs (s) | mean | spread |
|---|---|---:|---:|
| base | 32.813, 31.134, 30.758 | **31.568 s** | 2.055 s |
| candidate | 25.703, 24.680, 24.747 | **25.044 s** | 1.023 s |

**Δ = −6.52 s (−20.7%).** The arms do not overlap: the slowest candidate run is 5.1 s faster than the
fastest base run.

**Limitations.** Box-wide exclusivity was not available — other users held ~214% foreign CPU and two
compute apps on GPUs 0 and 1 throughout. The target GPU was exclusive (UUID preflight), foreign load
was recorded per arm and was flat across all six (213–220%), and the arm order alternated. `pcpu` from
`ps` is a process-lifetime average, so it bounds the foreign load's steadiness, not its instantaneous
value. This supports "faster under these conditions by a margin far exceeding within-arm spread"; it
is not a clean-room speedup figure, and n=3 per arm.

Attribution: the measured device-timeline saving is 75–126 ms/movie, i.e. ~1.8–3.0 s over 24 movies,
between roughly a quarter and a half of the 6.52 s. The remainder is host-side — the baseline's
per-element widening writes 1.273 GiB per movie where the candidate `memcpy`s 0.637 GiB, with the
matching reduction in first-touch page faults — but that share is inferred by subtraction, not
measured.

## 6. Test suites

| suite | result |
|---|---|
| CPU-only build, cpu64, `ctest` | **18/18 passed** (includes PR111's `GlobalIfftElision` and `CiFailClosedControls`) |
| CUDA build, 4GPUs, `ctest` | **20/20 passed** (adds `CudaU16StagingEquivalence`, `CudaWrapperUploadFailure`) |

`CudaU16StagingEquivalence` is additive rather than in `DEFAULT_REQUIRED_TESTS`, matching how
`CudaWrapperUploadFailure` is treated: it is only collected when `CUDA=ON` on Linux, so requiring it
would fail CPU-only CI.

## 7. What this does not establish

- One geometry, one codec, one GPU, one worker. No multi-GPU throughput measurement.
- Wall time: n=3 per arm on a shared box (see §5).
- H2D: bytes are exact and stated per movie; H2D *time* is n=2 and unstable.
- The host-side share of the 6.5 s is inferred by subtraction, not measured.
- The `−41.9%` RSS figure is the gain arm. The no-gain arm saves only 0.9%, because its
  non-converging patches materialise the float movie anyway.
- MRC mode 6 would take the same path with a one-line predicate change; untested, so excluded.
- EER, compressed MRC, packed 4-bit, signed 16-bit, 8-bit and float TIFF keep the existing float path
  by construction; not re-measured, and the CPU suite covers their behaviour.
- No claim of scientific equivalence: this is same-backend byte parity against the same main.
