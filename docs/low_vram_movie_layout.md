# Low-VRAM movie layout (opt-in, WIP)

Status: work in progress, stopped by the coordinator before the performance campaigns finished.
The layout is **off by default**. Enable it with `MOTIONCORR_CUDA_LOW_VRAM=1`, or call
`CudaMovieSession::setLowVram(true)` before `initialize()`.

## Layout

The default session holds two movie-sized device buffers: real frames (`d_Iframes`) and
their R2C spectra (`d_Fframes`). For the canonical 24-frame 3838x3710 movie, `d_Iframes`
is about 1.27 GB.

In low-VRAM mode `d_Iframes` aliases `d_Fframes`:

- **Forward FFT** runs frame by frame in *descending* order. Each frame is transformed
  out of place into `d_inverse_tile` and then copied to its own spectrum slot. Spectrum
  slot k (size ny*(nx/2+1) complex) starts at or after real slot k, so in descending
  order a write never overwrites a real frame that has not been read yet.
- **Inverse FFT** runs in *ascending* order. Before the real output of frame k overwrites
  spectrum slot k, that slot is spilled device-to-host into a thread_local pinned buffer
  (`t_fourier_spill`). The spill runs on a non-blocking stream and is ordered with events.
- **Dose weighting** first calls `ensureDeviceFourier`, which copies the host spectrum
  back to the device. After that the real frames are gone, and `downloadRealFrames` and a
  second forward FFT are refused.
- **State machine** (`LowVramContent`): RealFrames → FourierFrames →
  RealFramesHostFourier → FourierFrames, with Lost on any failure.
  `downloadFourierFrames` serves the host spectrum (`host_spectrum`) when the device copy
  has been overwritten, so the runner's CPU fallbacks still get the same bytes.
- The nvCOMP ingest arena and the sample arena move to `d_ingest_scratch` in this mode.

### Costs

- About 2 x 1.27 GB of PCIe traffic per movie.
- 1.27 GB of pinned host RAM per worker thread.

### Limitations

- If the forward FFT fails partway through with nvCOMP ingest, the run **fails closed**
  with no CPU fallback, because the real frames have been partly overwritten and no host
  copy exists.
- Movie dimensions must be even, as in the default layout.

## Exactness evidence (MEASURED, A100, GPU 3 on 4GPUs, commit 6048f7e)

**In-place versus out-of-place R2C** (`tests/cuda_fft_placement_probe.cpp`)
- 0 differing words at all 9 geometries tested, including 3838x3710, 7676x7420 and
  4096x4096, with cuFFT 11303.
- The layout does not rely on this result: it always transforms out of place through
  `d_inverse_tile`.

**Layout equivalence** (`CudaLowVramLayout`)
- Every product of the resident sequence is byte-identical between the two layouts:
  sums, spectra at each download point, global and batched patch shifts, per-patch
  preparation for 3 boxes x group sizes 1–3 (including an odd-sized box), and the
  dose-weighted sum.
- Geometries 256x192x7, 250x198x9 and 330x222x5: 63, 65 and 61 products compared,
  0 differ.

**Test suites**
- `MOTIONCORR_CUDA_LOW_VRAM=1 ctest -L cuda`: 20/20 pass.
- Default ctest: 62/62 pass. `CiFailClosedControls` fails only in a tree without
  `.git`; it passes in git clones.
- Low-VRAM fault matrix (`CudaFaultMatrixLowVram`): 288 trials, 0 failures.
- Coverage gap: the matrix does not wrap `cudaMemcpyAsync`, `cudaHostAlloc` or
  `cudaStreamCreate`.

**Compiled negative controls**

| mutant | change | result |
|---|---|---|
| M1 | forward FFT in ascending order | FAIL |
| M2 | `ensureDeviceFourier` returns early | FAIL |
| M2b | H2D copy skipped | FAIL: dose-weighted products differ |
| M3 | inverse FFT in descending order | FAIL: 171 products differ |
| M4 | `setLowVram` ignored | FAIL |
| M5 | failed destroy ignored | FAIL: fault matrix reports 2 failures |

## Performance

**Wall time: PARTIAL, no kit verdict.** The kit compare against base dfca087 with
`--env MOTIONCORR_CUDA_LOW_VRAM=1` was stopped after 9 paired rounds:
- candidate 10.8–15.7 s
- base 7.0–7.5 s

This points to a large regression, probably from the pinned spill and the PCIe round
trip. The cause has not been profiled.

**UNRUN**
- Peak VRAM (NVML and trace high-water).
- Per-stage deltas.
- Default-mode identity and no-regression campaign. The default path changed only by
  refactoring the ingest chunk selection and the sample arena variables.
- Long-movie case (no long-movie input exists).
