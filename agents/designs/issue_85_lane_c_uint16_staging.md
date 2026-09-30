# Issue #85 lane C: native uint16 TIFF staging with device-side conversion and gain

Status: prototype, measured, not proposed for merge. Base: main `8323c55`.

## Problem

For an unsigned-16-bit TIFF movie the reader widens every sample to float32 on the host before
anything else happens. The tutorial movie is 3710 x 3838 x 24, so the host holds 1.273 GiB and the
H2D copy carries 1.273 GiB, to deliver 0.637 GiB of information. The device needs float, but it does
not need the host to produce it.

## Change

When the input is unsigned-16-bit TIFF **and** the resident CUDA session will run, decode into
`Image<unsigned short>` instead of `Image<float>` and expand on the device.

The host side reuses the existing reader unchanged. `Image<T>::read` is already a template and
`castPage2T`'s `UShort` case already has an `unsigned short` branch — previously dead, since no
instantiation reached it. Selecting `T = unsigned short` therefore keeps every guard, the per-frame
geometry/format re-validation, the strip accounting and the per-row Y-flip exactly as they are, and
turns the per-sample conversion into a `memcpy`. No TIFF code was copied or modified.

The device side adds `CudaMovieSession::applyGainDefectsAndSumU16`, which uploads one frame at a time
into a single reusable `ny*nx` uint16 staging buffer and runs `convertGainAndAccumulateU16Kernel`.
A whole-movie uint16 device buffer was rejected: it would add 0.637 GiB to the device high-water and
convert a host-memory saving into a VRAM cost. One frame adds 27.16 MiB for the duration of the call.

Everything else keeps the float path: other TIFF sample formats, packed 4-bit, MRC, EER, compressed
MRC, the CPU path, and early binning.

## Why the products do not move

`uint16 -> float32` is exact: binary32 represents every integer up to 2^24 and the range is
[0, 65535]. So the device's `I2F.U16` yields the identical float the host cast produced, and every
later operand is unchanged.

Three things were deliberate rather than incidental:

- **No contraction.** The reference kernel's `val *= gain; d_Iframes[o] = val; sum += val` compiles to
  separate FMUL and FADD because the store gives the product a second use. Disassembly of the
  baseline object confirms FFMA 0, FMUL 30, FADD 59. The new kernel uses `__fmul_rn` and `__fadd_rn`
  so the same shape is guaranteed rather than inferred; its SASS is
  `LDG.E.U16 -> I2F.U16 -> @P0 FMUL -> STG.E -> LDG.E -> FADD -> STG.E`, FFMA 0.
- **The store is unconditional.** The float kernel writes `d_Iframes` only when a gain is applied,
  because there the H2D copy had already deposited the frame. With a uint16 upload nothing else
  writes it, and a no-gain movie would leave it uninitialised while `d_Isum` stayed correct — correct
  statistics over garbage frames, visible to no sum-based check. `CudaU16StagingEquivalence` covers
  exactly this case.
- **The accumulator is memset, not seeded.** The sum is now accumulated one frame per launch through
  `d_Isum`, which is exact because the reference accumulator is a float too. It is zeroed with
  `cudaMemset` rather than started from frame 0's value: the reference starts at `+0.0f` and
  `+0.0f + (-0.0f)` is `+0.0f`, whereas a seeded store would keep `-0.0f`. A zero sample against a
  negative gain entry produces exactly that product. A mutant that seeds instead is caught by the
  hostile-gain case of `CudaU16StagingEquivalence`.

`--first_frame_sum` / `--last_frame_sum` are handled by indexing the staging vector with the dense
frame index, as every other movie buffer does.

## Host consumers of the raw movie

Three, all retargeted:

| consumer | handling |
|---|---|
| hot-pixel neighbour read | reads `(float)u16`; the gain multiply and every RNG draw are unchanged |
| `materialize_host_frames` | widens first, then runs the existing in-place gain pass verbatim |
| CPU gain-and-sum fallback | widens first |

## Lifetime, and why it is not just "free it at the end"

The staging is released as soon as the resident forward FFT succeeds. Both `materialize_host_frames`
call sites are at or before that point, so no raw reader remains; after it, any fallback downloads
the aligned float frames from the device instead. Holding the staging longer is what made the first
version worse than main on the degraded path: a patch that does not converge downloads a fresh
1.273 GiB float movie, and in the candidate that landed on top of a still-live 0.637 GiB staging.

Releasing is not enough either. Each staged frame is a ~27 MiB `fftw_malloc`, which sits under
glibc's dynamic mmap threshold once that threshold has ratcheted up, so the arena kept the whole
0.637 GiB and the download still stacked on top — measured at 2.06 GiB against main's 1.52 GiB.
`drop_u16_staging` therefore calls `malloc_trim(0)` under `__GLIBC__`. With it the no-gain stress arm
is 1.50 GiB, below main.

`materialize_host_frames` fails loudly if it is ever reached after the drop with no float movie
present, rather than running its gain pass over an unallocated array.

## Relationship to PR107

None required. The change adds one method declaration after `applyGainDefectsAndSum`, one definition
after it, and one kernel in the existing anonymous namespace. It does not touch
`releasePreprocessingBuffers`, the `HANDLE_ERROR` block, `initialize`, `release`, or the runner's
patch loop — the regions PR107 modifies. The staging buffer is owned by a local RAII struct inside
the new method, so no member was added to `CudaMovieSession` and `release()` is untouched. The new
CTest entry is inserted before `CudaWrapperUploadFailure`; PR107 appends after it.

## Results

See `docs/issue85_laneC/RESULTS.md`. Summary: all 24 corrected MRCs and 25 STARs byte-identical in four
arm pairs; host RSS -0.637 GiB (-41.9%) on the gain arm; H2D -683.47 MB/movie (-47.6%); 24-movie wall
-20.7% (n=3, shared box); peak device memory unchanged.

## What this does not establish

Measured on one geometry, one codec, one GPU, one worker. No multi-GPU throughput result. The
conversion kernel costs +1.0 ms/movie, which is only negligible at this ratio of frames to pixels.
MRC mode 6 would take the same path with a one-line predicate change but has not been tested.
The RSS saving is a gain-arm figure: without a gain, non-converging patches materialise the float
movie anyway and the saving falls to 0.9%.
