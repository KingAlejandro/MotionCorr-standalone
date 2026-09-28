# Metal Backend Contract and Current Status

The Metal path is an **optional macOS prototype**. The build/dispatch work is
tracked by [#30](https://github.com/KingAlejandro/MotionCorr-standalone/issues/30);
the global alignment implementation is tracked separately by
[#32](https://github.com/KingAlejandro/MotionCorr-standalone/issues/32).
CPU-only builds remain the default and do not require Metal.

## Current prototype status

The current-main #32 implementation runs the weighted-reference, CCF, MPSGraph
inverse FFT, peak/subpixel, and Fourier phase-shift stages on an Apple Metal
device. A profile marker or device banner alone is not proof of that work: the
prototype writes `[Metal Global Alignment Completed]` only after all required
stages finish and the iterative alignment converges. Runtime and command-buffer
errors fail closed; there is no CPU fallback for a requested Metal run.

The implementation builds on macOS and has executed both seeded synthetic
fixtures on an Apple M4 Pro. It **does not yet pass the full relaxed Gate 2
comparison**. See [the #32 prototype report](metal_issue32_prototype.md) for
source, device, commands, complete metrics, and limitations. The CPU path and
the scientific acceptance gates have not been changed to make this prototype
pass.

## Interface

Declared in `src/acc/metal/metal_alignpatch.h` and implemented in
`src/acc/metal/metal_alignpatch.mm`:

```cpp
#ifdef _METAL_ENABLED

int metalGetDeviceCount();
std::string metalGetDeviceName(int device_id);

bool metalAlignPatch(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile
);

#endif
```

`Fframes` is the in/out collection of Fourier-transformed movie frames. The
pre-sized X/Y arrays receive the accumulated frame trajectories. `pnx` and
`pny` describe the real-space patch, `scaled_B` controls the CCF weighting,
`ccf_downsample` controls CCF resolution, and `device_id` is the zero-based
Metal device index.

## Execution contract

- `-DMETAL=ON` is opt-in and links the Apple Metal and MPSGraph frameworks.
- `--metal` selects global alignment on Metal; `--metal_device` selects the
  device. Invalid devices, unsupported builds, allocation failures, missing
  kernels/results, command-buffer failures, and nonconvergence fail the
  requested run. They do not silently select CPU alignment.
- Input Fourier frames are copied into shared Metal buffers. On Apple unified
  memory, those copies are host-memory copies; they are not reported as PCIe
  host/device transfers.
- The global path runs six witnessed stages: `weights`, `reference`, `ccf`,
  `ifft`, `peak`, and `fourier_shift`.
- The profile includes shared-buffer copy, kernel, MPSGraph, and total alignment
  times. A profile time alone is not a throughput claim.
- Local patch alignment and dose weighting stay on their existing paths.
- CPU-only/Linux builds must not acquire Metal framework or Objective-C++
  requirements.

## Completion marker

The per-movie log contains this line only after the alignment has converged and
shifted Fourier frames have been copied back:

```text
[Metal Global Alignment Completed] device_id=0 iterations=2 stages=weights,reference,ccf,ifft,peak,fourier_shift converged=true
```

The device number and iteration count vary by run. Harnesses should require the
complete ordered stage list, a matching requested device, at least one
iteration, and a positive total Metal alignment time. A historical dispatch
smoke marker is insufficient.

## History

Older #30 design notes and PR #42/#43 comments include a dispatch-smoke
verification phase. Those records describe earlier revisions and are not the
acceptance evidence for this current-main prototype. The current #32 report
records actual stage completion and preserves the Gate 2 failures.
