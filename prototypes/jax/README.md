# JAX global-alignment prototype (Issue #14)

This isolated prototype starts from MotionCorr main `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38`.
It is not imported by C++, adds no runtime dependency to MotionCorr, and does not implement
local patches, dose weighting, corrected frame stacks, or a production backend. It can write a
global-only unweighted sum for comparison.

## Contract copied from `MotioncorrRunner::alignPatch`

- Input arrays are `(frame, y, x)` float32 MRC mode-2 pixels. `rfft2` uses the last two axes and
  the R2C shape is `(ny, nx//2+1)`; rows remain in standard signed-frequency order.
- The C++ forward transform divides by `nx*ny`. The prototype does the same. The C++ inverse
  CCF is unnormalised; JAX's `irfft2` is normalized, so its correlation is multiplied by the CCF
  grid area. This changes correlation amplitude only, not peak locations or the parabolic fit.
- Each frame correlates `(sum(other frame spectra)) * conjugate(current frame spectrum)`, with
  the C++ weight `exp(-2*B*(x^2/nfx^2 + y_signed^2/ny^2))`, where `nfx` is the stored R2C
  half-spectrum width (`nx//2+1`) and `ny` is the real y dimension. Frequency cropping follows
  the signed-y packing used by C++. Automatic CCF sizing copies MotionCorr's good-size table.
- Peak search walks y then x over `[-search_range,+search_range]`; `argmax` uses the first maximum.
  The same 1-D quadratic interpolation and `1e-15` denominator guard are used on each axis.
- The C++ correlation returns corrective shifts. After each iteration shifts are made relative to
  frame 1, frame 1 is explicitly set to `(0,0)`, and all later frame Fourier images receive the
  negative-shift Fourier phase ramp. Convergence is `sqrt(sum(dx^2+dy^2)/nframes) < 0.5 px`,
  with a five-iteration default.

## Run

Create a CPU-only environment and run the committed small subpixel fixture:

```sh
python3 -m venv /tmp/motioncorr-jax
/tmp/motioncorr-jax/bin/python -m pip install -r prototypes/jax/requirements.txt
/tmp/motioncorr-jax/bin/python prototypes/jax/global_align.py \
  --input test-data/fixtures/synthetic_128x128_8frames_subpixel.mrcs \
  --output /tmp/jax-global-shifts.csv --corrected-sum /tmp/jax-global-sum.mrc --bfactor 150
```

JAX uses the first available device. On the tested Mac arm64 environment this is CPU. An installed
GPU backend can be selected with the standard JAX device environment/configuration, but no GPU
result is claimed here. The CSV stores 1-based frame numbers and C++-sign-convention `(x,y)` shifts;
the adjacent JSON records input identity, software/device, compilation, synchronized first/warm
execution, process peak RSS and backend memory counters where available. `block_until_ready()` is
used before timing stops.

The initial validation command on main's fixtures is:

```sh
/tmp/motioncorr-jax/bin/python prototypes/jax/test_global_align.py
```

This validates synthetic known motion and reference STAR shifts. It does not close Issue #14's
experimental-movie comparison or scientific-acceptance criteria. No reference threshold is changed.
