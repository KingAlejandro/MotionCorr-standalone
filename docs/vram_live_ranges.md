# Resident movie live ranges (low-VRAM Tier 1)

The resident CUDA path keeps two movie-sized buffers for the whole movie:
`d_Fframes` (half-spectra) and `d_Iframes` (real-space frames), 1304 MiB each on
the tutorial workload (24 × 3838 × 3710). Tier 1 lowers the stage peaks without
changing any value the pipeline computes, by (1) storing only the part of each
patch spectrum that patch alignment reads and (2) placing stage scratch in
`d_Iframes` while it holds nothing that is read later.

## Live ranges of `d_Iframes`

| Interval (runner order) | `d_Iframes` content | Read later? | Scratch placed there |
|---|---|---|---|
| ingest → gain/defect → sums | real-space movie | yes, forward FFT | none |
| forward FFT | input, read by the R2C | — | none |
| end of forward FFT → global alignment | stale movie | no: the inverse FFT rewrites every frame | **global alignment** buffers and cuFFT work area |
| global inverse FFT | rewritten from shifted `d_Fframes` | yes: patch preparation, unweighted sums | none |
| patch alignment | real-space movie | yes | none |
| unweighted reconstruction (`pre_dw_sum_needed`) | real-space movie | read here | none |
| dose-weighted reconstruction | real-space movie | only if `--save_noDW` or `--even_odd_split` | **DW scratch** when neither is set |
| after DW | dead for this movie | no | — |

`pre_dw_sum_needed = !do_dose_weighting || save_noDW || even_odd_split` is the
runner's existing predicate; the DW call passes `consume_real_frames =
!pre_dw_sum_needed`, so both borrows follow the same test the reconstruction
order already uses.

## Ownership and refusal

`CudaMovieSession` records why `d_Iframes` is invalid
(`real_frames_invalid_reason`). While it is set, every reader refuses with
`ERROR: refusing <operation>: the device real-space movie is no longer valid
(<reason>)` and returns false: the forward FFT, patch preparation, the
unweighted reconstruction and the real-space frame download. A refusal does not
set the session failure state, so the #69 contracts (recoverable failure → the
existing host fallback, fatal context → no fallback) are unchanged.

- Global borrow: `borrowRealFramesForGlobalAlignment` sets the reason, a
  successful `computeGlobalInverseFFT` clears it. The resident path always runs
  that transform (the inverse-FFT elision is host-only); if it fails, the runner
  downloads `d_Fframes` and resets the session, so the borrowed buffer is never
  read.
- DW borrow: set by `reconstructDoseWeighted(..., true)` and never cleared for
  that movie. The CPU dose-weighting fallback after a recoverable resident
  failure refreshes from `downloadFourierFrames`, which the scratch does not
  touch.
- The DW scratch (`doseScratchLayout`, about 2.5 frames) is carved only when it
  fits in `n_frames` frames; otherwise it is allocated as before. The per-movie
  log states `Dose-weighting scratch borrowed from the consumed real-space
  movie` when it is carved.

## Global alignment arena

`cudaAlignPatchDeviceInArena` carves the reference, weight, CCF and shift
buffers (each 512-byte aligned) from the arena, then the cuFFT work area if it
also fits; a work area that does not fit is allocated alone, and buffers that do
not fit fall back to the existing allocations. Kernels, plan configuration and
order are those of `cudaAlignPatchDevice`. The log adds one placement line
(`..., nothing allocated` or `...; cuFFT workspace allocated`); the
`Buffer VRAM` and `Peak` lines are unchanged.

## Windowed patch spectra

Patch alignment reads only the CCF window of each patch spectrum: `ccf_ny` rows
of `ccf_nx/2+1` (`patchSpectrumWindow`), row `y` of the window being spectrum
row `y` for `y <= ccf_ny/2` and row `y - ccf_ny + pny` above it.
`cudaExtractPatchWindow` copies that window after the R2C and applies the
normalisation scale in the same operation and order as `scaleComplexKernel`, so
every value read is bit-identical. The phase shift is applied with the original
frequency coordinates, so shifted values are identical too. Both the batched
slots and the per-patch buffer store windows only; the full spectrum lives in
session scratch (`d_inverse_tile`, or `d_patch_spectrum` when that is too
small) for one patch at a time. Global alignment is unchanged.

The per-patch log line `Peak GPU memory allocated` counts the spectrum stack it
was given, so it reports the window size in window mode; that number drops.

## Measured effect (tutorial, A100, CUDA 12.8)

Traced device-allocation high-water per stage, MiB (kit `mem peak MiB`, 24
movies; evidence in `docs/perf_vram_tier1/`):

| Stage | main | default | `--save_noDW --even_odd_split` |
|---|---|---|---|
| global alignment | 3143 | 2877 | 2877 |
| patch alignment | 3221 | 3026 | 3026 |
| dose weighting | 3117 | 2877 | 3013 |
| movie peak | 3221 | 3026 | 3026 |

Ingest (2932 MiB) and the global FFT/iFFT (2877 MiB) are unchanged. With the
alias off (second column), only dose weighting differs from the default, as
designed. Per movie, the batched patch workspace drops from 236 to 41 MiB and
the per-patch `Buffer VRAM` from 236.49 to 41.42 MiB.
