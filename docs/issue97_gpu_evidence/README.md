# Issue #97 — native CUDA validation (4GPUs)

Closes the "CUDA / GPU execution" item that the CPU evidence listed as UNRUN.
**Correctness only. No timing was measured and none is claimed.**

| file | contents |
|---|---|
| `4gpus_cuda_build.log` | raw CUDA build of both trees |
| `4gpus_cuda_run.log` | raw run: device witness, all 8 arms, accumulated motion |
| `4gpus_product_comparison.log` | product comparison |
| `gpu_build.sh`, `gpu_run.sh` | the exact scripts |

## Host and devices

`4-gpu-vm`, 4 x NVIDIA A100 80GB PCIe, driver `570.86.10`, CUDA 12.8.61.
Devices recorded by **UUID**, because ordinals do not identify silicon:

```
0  GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
1  GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d
2  GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598
3  GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
```

Run pinned to `taskset -c 96-103` (the 8-logical-CPU cap for this shared box), `-j8`,
single device `--gpu 0`.

**Concurrency, disclosed.** A probe ~10 minutes before the run showed all four GPUs idle.
By run time they were not: two `python` processes belonging to a different user
(`ryz18496`) held 61,302 MiB each on devices 0 and 1, and `nvidia-smi` shows them present
both before and after. **My run therefore shared device 0 with another user's job.**
That cannot affect correctness — GPU contention changes timing, not arithmetic — and no
timing is claimed here. It does mean this box was not exclusive, so these runs must never
be relabelled as timing evidence. The `/tmp/motioncorr-bench.lock` was acquired (free, 0s)
so this run could not perturb a concurrent *benchmark*; note the other user's job did not
hold that lock, which is consistent with the lock being advisory only.

## Build provenance

Two separate source trees, each cloned and configured independently.

| tree | commit | binary sha256 |
|---|---|---|
| base | `8323c55` (origin/main) | `4c79d6b1451c7a4689f9d722903e4a33b3ffcf54783286920355e4132a9d3b8b` |
| fixed | `95c0cfb` (branch with main merged in) | `959f1b8b9f8a77ce5af543673780556a8c7ccc76e50859d4013ca55a339d8c68` |

Both link `libcudart`. `CMAKE_BUILD_TYPE=Release`, `CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=80`.

### Two build findings worth reporting upstream of this PR

1. **`-DCMAKE_CUDA_ARCHITECTURES=80` had to be passed explicitly.** The project's
   `if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES) set(... 80)` guard does not fire under
   CMake 3.28 + CUDA 12.8, because `enable_language(CUDA)` has already defined the
   variable. The first attempt configured with `52` in the cache and then failed generation
   with `CUDA_ARCHITECTURES is empty for target "motioncorr_core"`. This is a defect in the
   repo's CMake on this toolchain combination, not in this PR, and is not fixed here.
2. **`BUILD_TESTING=ON` is impossible on this host.** Current main hard-fails configure with
   `BUILD_TESTING=ON requires Python 3 with 'numpy' installed`, and 4GPUs has no numpy. The
   CUDA builds here therefore use `BUILD_TESTING=OFF`, so **no ctest suite was run on the GPU
   host** — only the integration arms below.

A note on how the first attempt failed: configure failed, yet the driver script still
reported `build exit=0` and produced a cudart-linked binary. That would have been a green
result from a failed configure. The scripts retained here abort on a non-zero configure or
build rc.

## Inputs — identical to the CPU run

```
f989391b9d0e3e3b927a8de59d60179ade0b7ae5075ce7c3a9a5002ae2254ae3  20170629_00026_frameImage.tiff
8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1  gain.mrc
44f32752ebb62fc22428e95a1449e54e3a6952036285b805b96085f296ec5ed0  synthetic_128x128_8frames.mrcs
```

These hashes match the cpu64 inputs byte for byte, so the CPU and GPU runs are on provably
identical data.

## The GPU actually executed the path the fix touches

This matters: the fix lives in the **local/patch** recentering, so a GPU run that only
accelerated global alignment would not exercise it. The per-movie logs show both:

```
[CUDA Global Alignment Profile]   ... completed; converged=yes
Local alignments:  Patches: X = 5 Y = 5
[CUDA Patch Alignment Profile]    ...
```

All 8 arms exited 0, with 9 patch blocks (3x3 synthetic) and 25 (5x5 real movie). So the
`local_xshifts`/`local_yshifts` fed into `interpolateShifts` and then into
`recenterShiftsToFirstFrame` were produced by the CUDA patch kernel.

## Results

### Default-off exactness control — UNCHANGED on CUDA

| product | synthetic 3x3 | real movie 5x5 |
|---|---|---|
| output `.mrc` pixel payload | **IDENTICAL** | **IDENTICAL** (56,955,920 bytes) |
| per-movie `.star` motion model | **byte-identical** | **byte-identical** (779 lines) |
| joint `corrected_micrographs.star` | identical (values compared) | identical (values compared) |

### Option-on — INTENTIONALLY CHANGED on CUDA

| product | synthetic 3x3 | real movie 5x5 |
|---|---|---|
| output `.mrc` pixel payload | DIFFERS | DIFFERS |
| per-movie `.star` | DIFFERS in 99/164 lines | DIFFERS in 611/779 lines |
| joint `corrected_micrographs.star` | EQUAL | EQUAL |

Accumulated motion, all four arms per input:

```
gpu-mov-*   1 13.154425 1.827993 11.326432
gpu-syn-*   1  4.333531 1.393570  2.939961
```

`GATE: PASS` — all four controls as expected.

Per-pixel difference statistics are absent from the GPU comparison because this host has no
numpy; the comparator degrades to byte-level verdicts, which are what the controls rest on.

## Limits

- **No timing claim.** Shared box, another user's job resident on the same device.
- **No CPU/GPU parity claim.** The GPU accumulated-motion values differ slightly from the CPU
  run (`13.154425` vs `13.167835`), as expected for a different backend. Nothing here asserts
  cross-backend equality; each backend is compared only against itself.
- **No ctest suite on the GPU host** (numpy absent, see above). The unit regression is covered
  on cpu64.
- **No downstream scientific claim**, no FSC/B-factor/RELION comparison.
- One real movie, one synthetic fixture, two patch geometries, single device.
