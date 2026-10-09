# `--fft_size_policy {exact,fast}`

Base: `main` `7d64043`. Hardware: 4GPUs, A100 GPU3 (`GPU-b2cb2c39-…`),
payload CPUs 80-87.

## Summary

`--fft_size_policy fast` transforms CUDA frames and patches at the next even
7-smooth size, padded with the mean. The default `exact` is byte-identical
to `7d64043`.

- **Speed: about 13% faster, but the products differ.** On 96 tutorial movies
  the median paired wall-clock difference is −3.48 s of 25.9 s, and the kit
  verdict is "speed only, products differ".
- **The mode fails the gates.** It fails the blocking backend gate against
  the CPU path on 24/24 tutorial movies, where the default passes 24/24. It
  also fails one known-motion implementation gate on a non-smooth fixture.
- **The cause is intrinsic to padding, not a defect.** Frame padding
  replaces the wrapped edge strip with the mean (a flat ~0.3% power loss),
  and patch padding changes the local fits by up to 0.36 px. Padding only
  the patches still fails 21/24 and would keep about 5% (Diagnosis).
- **It is therefore experimental:** hidden from `--help`, and not a
  candidate for a default. The gates are too coarse to catch a 1%
  dose-weight grid error in this mode; `CudaFftSizePolicy` covers that.

## Microbenchmark (MEASURED)

`tools/fft_size_bench/fft_size_bench.cu`, cuFFT single-precision R2C and C2R,
median of 50 executions after 3 warm-up runs, out of place, batch as MotionCorr uses it (frame: 1,
patches: 24 groups). Raw table: `fft_size_policy/microbench.tsv`.

| case | exact size | exact R2C ms | 7-smooth size | 7-smooth R2C ms |
|---|---|---:|---|---:|
| tutorial frame | 3710×3838 | 0.84 | 3750×3840 | 0.39 |
| tutorial patch 3×3 | 1236×1278 ×24 | 2.13 | 1250×1280 | 0.71 |
| tutorial patch 5×5 | 742×766 ×24 | 0.61 | 750×768 | 0.25 |
| tutorial patch 7×7 | 530×548 ×24 | 0.32 | 540×560 | 0.13 |
| K3 frame | 5760×4092 | 0.65 | 5760×4096 | 0.52 |
| K3 patch 5×5 | 1152×818 ×24 | 0.72 | 1152×840 | 0.50 |
| Falcon 4 frame | 4096×4096 | 0.29 | 4096×4096 | 0.29 |
| Falcon 4 patch 5×5 | 818×818 ×24 | 0.68 | 840×840 | 0.33 |

C2R times match R2C to within 3%. 5-smooth and 3-smooth sizes are no faster
than 7-smooth. Multiplying by the per-movie transform counts of the tutorial
5×5 run gives an upper bound of about 40 ms of ~232 ms of GPU FFT work per
movie (CALCULATED, not a wall-clock claim). The kit compare below measures
the wall-clock effect.

## Design

`fast` applies only to the resident CUDA movie session.

- **Frames.** `CudaMovieSession::setFftSizePolicyFast` sets the transform
  extent to `fnx×fny = fastFftSize(nx)×fastFftSize(ny)`, the next even
  7-smooth sizes. The forward FFT copies each frame into a dense `fnx×fny`
  tile padded with that frame's mean (computed on the device), runs the R2C
  and scales by `1/(fnx·fny)`. The inverse runs a C2R at the padded size in
  place and crops the `nx×ny` frame back (`cropFrameKernel`, stride
  `2·fnfx`).
- **Every frequency-space consumer uses the padded grid.** Global alignment
  (`alignPatchDevice`) gets `fnx×fny`, so its B-factor, CCF and sub-pixel
  shifts are in padded-grid frequencies, and shifts in pixels are unchanged.
  The phase shift applied to the resident spectra and the dose weighting
  (`cudaDoseWeightAndInterpolateDevice`, new `fft_nx/fft_ny`) also use the
  padded grid. The weighted sum is inverted at the padded size and cropped.
- **Patches.** `preparePatchInVram` pads each group sum to
  `patchFftExtent(patch_w)×patchFftExtent(patch_h)`. The pad value is the
  group's sum of frame means, so the pad matches the group sum's level. The
  CCF window and the patch aligner use the padded extents.
- **Outputs** keep the movie's dimensions and pixel size. The log records
  `FFT size policy fast: frame NXxNY transformed at FNXxFNY`.
- **Not applied:**
  - with `--grouping_for_ps > 0`, because the power spectrum is written from
    the resident spectra and keeps the exact grid. A log line says so.
  - with early binning, which runs without a session.
  - on the CPU path, which always transforms at exact sizes. `fast` changes
    nothing in a CPU-only build or a run without `--gpu`.
- **CPU fallbacks.** When the resident inverse FFT or the resident dose
  weighting fails recoverably, the runner downloads the padded spectra.
  `exactSpectraFromPadded` inverts them at the padded size, crops and
  re-transforms at `nx×ny`. From there the movie continues as under `exact`.
- **Default.** `exact` sets `fnx=nx, fny=ny`. No new kernel runs, the same
  plans are created, and the products are byte-identical (below).

Padding with the mean, unlike zero padding, avoids a step at the frame edge.
Content beyond `nx×ny` is not periodic with the frame, so the padded
transform's spectrum differs from the exact one. Products therefore differ
from `exact` in the low bits and at sub-pixel level. The validation measures
how much.

## Default-policy identity (MEASURED)

`fft_size_policy/scripts/identity.sh` compares base `7d64043` with this branch,
4 tutorial movies (`--j 8`, GPU3). It uses the kit identity rule
(`cmp_trees.py`): MRC bytes 0-223 and from 1024, other files byte-identical
after path normalisation, logs excluded, PDFs inventoried. Raw:
`fft_size_policy/identity.txt`.

| configuration | base vs branch |
|---|---|
| GPU, nvcomp, even/odd | IDENTICAL |
| GPU, + `--save_noDW` | IDENTICAL |
| GPU, `--bin_factor 1.25 --no_early_binning` | IDENTICAL |
| GPU, `--grouping_for_ps 4` | IDENTICAL |
| CUDA build, CPU path | IDENTICAL |
| CPU-only build | IDENTICAL |
| mixed sizes (3 tutorial + 2 crops), GPU | IDENTICAL |
| mixed sizes, CPU path | IDENTICAL |
| `MOTIONCORR_FRAME_POOL_POISON=1`, tutorial and mixed | IDENTICAL, IDENTICAL |
| explicit `--fft_size_policy exact` | IDENTICAL |
| `--fft_size_policy fast --grouping_for_ps 4` | IDENTICAL (fast ignored, logged for all 4 movies) |
| control: `--fft_size_policy fast` | DIFFERENT |
| control: base with vs without `--save_noDW` | DIFFERENT |

The controls show that the comparator sees both a changed product and the
fast policy.

## Tests

- `CudaFftSizePolicy` (`tests/cuda_fft_size_policy.cpp`) compares each
  session product against an independent host-padded pipeline with its own
  plans, on a 262×254 frame that pads to 270×256:
  - `fastFftSize` values;
  - forward spectra of the mean-padded frame, byte-equal;
  - the cropped inverse returns the original frame;
  - patch spectra of the mean-padded group sums, byte-equal;
  - dose weights on the padded frequency grid, polynomial and direct paths.

  Five compiled mutants must fail it, and do: `dw_unpadded_weights`,
  `dw_dense_stride`, `frame_pad_zero`, `patch_pad_zero` and
  `crop_dense_stride`.
- `CudaFftSizePolicyFallbacks` (`tests/run_fft_policy_fallback_controls.py`).
  It uses the test-only fault shim on a 62×46 movie, which pads to 64×48. Two
  injected recoverable failures send a fast run through each CPU fallback:
  `ifft-crop-recoverable` (resident inverse) and `dw-alloc-recoverable`
  (resident dose weighting). Each run must witness the injection, exit 0,
  release all CUDA allocations and write products of the movie's own size.
  The test also checks that `--help` does not list `--fft_size_policy`.
  Measured on GPU3:

  | comparison (relRMSE) | value | bound |
  |---|---:|---:|
  | noDW, either fallback vs healthy fast | ≤ 6e-7 | 1e-5 |
  | DW, the two fallbacks vs each other | 7.3e-7 | 1e-5 |
  | DW, either fallback vs healthy fast | 0.0042 | < fast vs exact |
  | DW, healthy fast vs healthy exact | 0.051 | |
  | either product, 1-pixel offset | 0.61 | |

  A fallback weights on the exact grid and the healthy fast run on the padded
  grid. The 0.0042 is that difference. The fixture's pad is 4% of the frame,
  so the difference is larger than on real movies.

  Compiled negative control: the same binary built without the two
  `exactSpectraFromPadded` calls (a source copy with those two lines deleted,
  `motioncorr_faultinject` target) fails the test.
  - The inverse-fault case aborts with exit -6 (CUDA invalid argument in the
    dose weighting).
  - The DW-fault case exits 0 but writes a corrupt DW sum: relRMSE 1.43 vs
    healthy fast, rejected by the DW bound.

  Both MEASURED.
- Validation also runs a whole-binary mutant, `motioncorr_fft_dw_mutant`
  (dose weights on the unpadded grid). The backend gate does not detect it
  (Numerical validation, Negative control).
- Full suites (MEASURED): CUDA Release ctest 79/79 on GPU3 at the final
  source, including `CudaFftSizePolicyFallbacks` and the fault matrix.
  CPU-only ctest 44/44 before the fallback test was added (that test needs
  CUDA).

## Numerical validation (MEASURED)

`fft_size_policy/scripts/validate.sh` on GPU3, 24 tutorial movies, `--use_own
--dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
--j 8 --save_noDW`, nvcomp ingest. Four arms: CPU path (`cpu`), default GPU
(`gpu`), `--fft_size_policy fast` (`fast`) and the whole-binary DW mutant with
fast (`mut`). Trees are compared by `validate_compare.py`, which calls
`compare_motioncorr.py --gate backend` per movie. The limits are unchanged:
the blocking backend gate is max shift error 0.05 px, RMS shift error 0.02 px,
image RMSE 0.02 and max pixel error 5.0; relRMSE ≤ 1e-3 is a non-blocking
diagnostic. Raw: `fft_size_policy/val/` (`validate.txt`, `*_vs_*.json`).

**Tutorial movies, dose-weighted sums** (maxima over 24 movies):

| comparison | backend PASS | max shift px | RMS shift px | image RMSE | max px err | relRMSE | PS dev | min r |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu → gpu (default baseline) | **24/24** | 0.0128 | 0.0081 | 0.0094 | 3.01 | 0.0104 | 0.0017 | 0.99995 |
| cpu → fast | **0/24** | 0.0390 | 0.0248 | 0.0494 | 4.29 | 0.0597 | 0.0085 | 0.99822 |
| gpu → fast | **0/24** | 0.0451 | 0.0265 | 0.0492 | 4.29 | 0.0606 | 0.0084 | 0.99817 |
| fast → mut | 24/24 | 0 | 0 | 0.0016 | 0.013 | 0.0017 | 0.0007 | 0.999999 |

Under `cpu → fast` every movie fails on image RMSE (0.028–0.049 > 0.02), and
movie 00028 also fails on RMS shift error (0.0248 > 0.02). The default passes
all 24.

**noDW sums.** The backend gate fails 0/24 already for the default (cpu → gpu
image RMSE up to 0.062, max pixel error up to 10), so it does not separate the
arms. Fast is further off: cpu → fast RMSE up to 0.45, max pixel error 28.7,
relRMSE 0.125 (default 0.016).

**Local trajectories** (all 24 × 25 patches × 24 frames matched): cpu → gpu
max deviation 0.065 px, max per-movie RMS 0.014 px; cpu → fast 0.71 px and
0.13 px; gpu → fast 0.72 px and 0.13 px.

Fast is equally far from the CPU and the default GPU, so the difference is the
policy, not GPU-versus-CPU arithmetic. Where it comes from is under Diagnosis.

**Negative control.** The whole-binary DW mutant (fast, but dose weights built
on the unpadded grid) differs from fast by relRMSE 0.0017, and the backend
gate passes it 24/24. The gates are too coarse to validate frequency-grid
consistency in this mode: a grid error of 1% of each axis is below their
resolution, and fast itself already fails them. The discriminating control
for the grid is `CudaFftSizePolicy` (byte-equal spectra plus five compiled
mutants, under Tests).

**Known-motion gates** (`tools/run_known_motion_gates.py --include-heavy`,
#60/#61 limits, raw `val/km_*.txt`). Every canonical fixture is already
7-smooth (512², 768×512, 2048²), so fast pads only the patches:

| fixture | default total Å | fast total Å | mut total Å |
|---|---|---|---|
| km_global_hisnr | PASS 0.0079 | PASS 0.0079 | PASS 0.0079 |
| km_local_hisnr | PASS 0.0526 | PASS 0.0526 | PASS 0.0526 |
| km_local_nonsquare | PASS 0.0421 | PASS 0.0421 | PASS 0.0421 |
| km_local_noisy (characterization) | FAIL 0.660 | FAIL 0.660 | FAIL 0.660 |
| km_local_realscale | PASS 0.1543 | PASS 0.1688 | PASS 0.1688 |

To exercise frame padding, `scripts/kmns.sh` generated two uncommitted
fixtures at non-smooth sizes with the canonical generator
(`scripts/kmns_cases.diff`). Each is one replicate (raw `val/kmns_*.txt`):

| fixture (padded to) | default | fast |
|---|---|---|
| km_local_hisnr_ns 506×494 (512×500) | PASS, total 0.0356 Å | **FAIL**: applied_image_self_consistency; total 0.0747 Å, global 0.0274 Å (default 0.0052) |
| km_local_realscale_ns 1854×1918 (1890×1920) | PASS, total 0.1935 Å | PASS, total 0.1869 Å |

The self-consistency gate re-applies the reported field to the raw movie with
periodic wrap and compares the result with the program's sum. Fast fails it
with relRMSE 0.0061 against a floor of 1e-4 (max error 275). Excluding a border
twice the 8.2 px maximum field, fast agrees to 4.4e-6 (default 2.1e-6). So the
pixels match the reported field, and the failure is the wrap band: fast fills
it with the frame mean where the gate wraps the opposite edge. The gate is not
relaxed, so this is a FAIL.

The known-motion fixtures are periodic by construction, which suits exact
transforms. The doubled field error on km_local_hisnr_ns is a single replicate
on such a fixture, and km_local_realscale_ns moves the other way. The data do
not establish that fast is less accurate on real movies, only that it is
different. Known-motion gates measure the field, so the DW mutant is invisible
to them, as expected.

**Verdict.** Fast fails the blocking backend gate on all 24 movies, where the
default passes all 24. It also fails a blocking known-motion implementation
gate on a non-smooth fixture. The option therefore stays experimental and is
hidden from `--help`. `CudaFftSizePolicyFallbacks` checks that it is not
listed.

## Diagnosis (MEASURED)

The question was whether the image-RMSE failure is a reconstruction defect
(padding leaking into the crop, a DW or B-factor grid on the wrong size,
border interpolation) or intrinsic to padding. It is intrinsic. Both the
frame padding and the patch padding change the products beyond the gate on
their own, and no DW-grid or crop error is involved.

**Power-spectrum ratio** (fast/gpu, 10 bands to Nyquist, mean over 24 movies,
from `val/*_vs_*.json`): DW sum 0.9973, 0.9982, 0.9985, 0.9986, 0.9985,
0.9983, 0.9980, 0.9978, 0.9976, 0.9975; noDW sum ~0.997 in every band; per
movie, band 0 ranges 0.9955–0.9985. cpu → gpu is 1.0000–1.0001. A flat
loss that includes the lowest band and the unweighted sum excludes the DW
grid (the mutant moves the DW power by at most 0.0006 and noDW not at all)
and is not the high-frequency attenuation of alignment blur. It matches the
wrap band. After a global shift s, the exact transform wraps real signal
from the opposite edge into an s-pixel strip; the padded transform fills
that strip with the frame mean. The tutorial y pad is 2 px (3838 → 3840), so
no choice of pad content can reproduce the wrap for shifts of several
pixels.

**Split by padded transform.** `scripts/diag.sh` ran a scratch build of
this branch with a switch that pads only the frames (global alignment,
shifted inverse, dose weighting) or only the patches
(`diag/diag_switch.diff`, not part of the PR). Same 24 movies and options
as above; raw `diag/`.

| arm vs gpu (DW sum) | backend PASS vs cpu | global max shift px | local max / RMS px | image RMSE max | interior RMSE / σ | squared error in outer 8 px |
|---|---:|---:|---:|---:|---:|---:|
| default gpu (cpu → gpu) | 24/24 | 0.013 | 0.065 / 0.014 | 0.0094 | 0.006 | 18% |
| fast (both) | 0/24 | 0.045 | 0.72 / 0.13 | 0.049 | 0.036 | 39% |
| frames only | 0/24 | 0.045 | 0.74 / 0.086 | 0.046 | 0.021 | 58% |
| patches only | 3/24 | 0 | 0.36 / 0.12 | 0.038 | 0.027 | 9% |

"Interior" is ≥ 128 px from every edge; RMSE / σ and the edge share are
medians over 24 movies (`scripts/errmap.py`). The outer 8 px are 0.8% of
the area.

- **Frames only:** the error is concentrated in the wrap band (58% of the
  squared error in 0.8% of the area). The rest follows from the slightly
  different global shifts, since a subpixel Fourier shift rings the
  different edge discontinuity into the interior.
- **Patches only:** the global shifts are bit-identical to the default, but
  the local fits move by up to 0.36 px, five times the CPU-versus-GPU
  spread. The error map (`diag/map_gpu_vs_patches.png`) is a smooth field
  across the whole micrograph with zero-crossing lines, the signature of a
  changed fitted motion model, not of a crop or edge defect. A mean-padded
  patch has a different boundary than a circularly wrapped one, and at
  tutorial SNR that shifts the cross-correlation peaks by tenths of a pixel.
  The canonical known-motion gates, where fast pads only the patches, still
  pass, so the changed fits are within the #60 accuracy limits; they are
  not within the backend gate, which asks for agreement with the CPU.

**Alignment-only padding.** Padding only the patches fails 21/24 and would
keep the patch-alignment saving only (−10.8 ms of 234.6 ms per movie, ~5%,
calculated from the stage profile; UNRUN as wall time). Padding the
global-alignment transform while reconstructing at exact size is not cheap
in this design: one resident forward FFT feeds both global alignment and
reconstruction, so exact reconstruction needs a second forward transform
(24 frames × 0.84 ms ≈ 20 ms per movie, calculated from the microbenchmark), which cancels most of the frame
saving. Neither variant is worth pursuing under the current gates.

## Speed (MEASURED)

**IDENTITY FAILURE.** In both kit compares, the fast products differ from
the default's: MRC payload and header, STAR shifts, and EPS plots. The kit
ran with `--allow-product-difference`, so its verdicts are "speed only,
products differ". They say nothing about whether the products are
acceptable; the validation above says they fail the gates.

Both compares used the kit (`tools/kit-products-differ`, `cc82b8d`) with
12 paired rounds and ABBA order. The arms were `build/motioncorr` with and
without `--fft_size_policy fast`, built from this branch. Payload options:
`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest
nvcomp`. Lane: CPUs 80-87, runner CPU 119, GPU3. Reports, compare.json and
provenance are in `fft_size_policy/kit96/` and `fft_size_policy/kit24/`.

| input | default wall median s | fast wall median s | median paired Δ s | CI of median s | sign | relative | verdict |
|---|---:|---:|---:|---|---|---:|---|
| 96 movies (`data96`), load1 13–23 | 25.882 | 22.643 | −3.475 | −5.586..−2.096 | 0+/12− | −13.4% | speed only, products differ: faster |
| 24 movies (`movies.star`), load1 14–21 | 7.186 | 6.131 | −0.904 | −1.203..−0.626 | 2+/10− | −12.6% | speed only, products differ: faster |

Results from the 96-movie profiled passes (steady median per movie, 3
passes per arm): movie wall 234.6 → 199.1 ms. Most of the gain comes from:

| stage | change ms |
|---|---:|
| patch alignment | −10.8 |
| dose weighting | −9.3 |
| global FFT | −7.8 |
| global IFFT | −7.1 |
| release preprocessing | +1.7 |

The release cost is the per-movie free of the padded buffers. The total is
close to the microbenchmark's calculated bound of ~40 ms per movie.

The 24-movie profile gives 227.9 → 191.1 ms per movie. The host was shared
(load1 13–23). The kit discarded rounds with foreign CPU on the lane (1 of
13 for 96 movies, 4 of 16 for 24) and kept 12 clean rounds each.

## Limitations

- CUDA only. The CPU path is exact.
- The fallback controls inject status codes. Genuine device faults are
  untested.
- Validated on the tutorial geometry (3710×3838, 24 frames, 5×5 patches) and
  the known-motion fixtures. The canonical fixtures are 7-smooth; the two
  non-smooth fixtures are uncommitted scratch cases, one replicate each.
  Other detectors are covered only by the microbenchmark.

## Reproduction

Scripts in `fft_size_policy/scripts/`: `identity.sh` (default identity matrix,
compared by `cmp_trees.py`), `validate.sh` (24-movie gates and known-motion
gates, compared by `validate_compare.py`). Kit commands are listed under
Speed.
