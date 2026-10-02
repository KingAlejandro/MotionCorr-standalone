# Metal Backend Interface Contract

This document specifies the C++ backend dispatch interface, memory model, calling conventions, error propagation, and verification markers established in **Issue #30** for the Apple Metal global alignment implementation in **Issue #32**.

---

## 1. Scope & Architectural Boundaries

- **Issue #30 (this track)** owns:
  - CMake build switch (`-DMETAL=ON/OFF`) and framework linkage (`Metal.framework`, `Foundation.framework`).
  - CLI selection flags (`--metal`, `--metal_device <id>`) and validation.
  - Fail-closed device discovery and dispatch routing.
  - Narrow C++ header interface (`src/acc/metal/metal_alignpatch.h`) and smoke dispatch.
  - Verification of Apple Silicon host environment and CPU parity preservation.

- **Issue #32** owns:
  - Metal compute kernels (cross-correlation surface calculation, 2D real-to-complex / complex-to-real FFTs or Apple vDSP/MPS/Metal FFT pipelines, Jasenko peak search, subpixel interpolation, Fourier phase shifts).
  - Iterative global frame alignment loop replacing the dispatch smoke stub.

- **Issue #33** owns:
  - Synthetic CPU-versus-Metal regression test harness modeled after `tools/run_cuda_synthetic_regression.py`.

---

## 2. Dispatch Function Signature

Declared in [`src/acc/metal/metal_alignpatch.h`](../src/acc/metal/metal_alignpatch.h) and compiled in [`src/acc/metal/metal_alignpatch.mm`](../src/acc/metal/metal_alignpatch.mm):

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

#endif // _METAL_ENABLED
```

### Parameter Contracts

| Parameter | Type | Semantics & Pre-conditions |
| :--- | :--- | :--- |
| `Fframes` | `std::vector<MultidimArray<fComplex> >&` | In-place / read Fourier frames. Each element has shape $[(pny/2 + 1) \times pnx]$. Issue #32 uploads these frequency-domain frames to Metal buffers. |
| `pnx`, `pny` | `const int` | Patch dimensions in X and Y (even integers, power of 2 or composite FFT size). |
| `scaled_B` | `const RFLOAT` | B-factor scaling parameter for cross-correlation weighting filter. |
| `xshifts`, `yshifts` | `std::vector<RFLOAT>&` | Output drift trajectories (length $N_{\text{frames}}$). Pre-sized by runner. Populated with cumulative shifts relative to frame 0. |
| `max_iter` | `const int` | Maximum iteration count (default 5). |
| `ccf_downsample` | `const RFLOAT` | Downsampling factor for CCF surface. |
| `device_id` | `const int` | Validated zero-based index of the selected Metal GPU device. |
| `logfile` | `std::ostream&` | Output stream pointing to `<movie_basename>.log` for logging profile markers. |

---

## 3. Apple Silicon Memory Architecture & Buffer Management

Apple Silicon (M-series) uses a **Unified Memory Architecture (UMA)** where CPU and GPU share physical DRAM:

1. **Storage Mode**:
   - Use `MTLResourceStorageModeShared` for input/output staging buffers to permit zero-copy or direct CPU-GPU pointer sharing without discrete PCIe transfers.
   - For internal intermediate scratch buffers (e.g. CCF maps, FFT working buffers) that are only accessed by GPU compute pipelines, `MTLResourceStorageModePrivate` may be utilized for cache optimization.

2. **Buffer Lifetimes & Scoping**:
   - Device resources (`id<MTLDevice>`, `id<MTLCommandQueue>`, pipeline state objects) must be allocated once per runner/session or cached across movies to avoid reallocation overhead.
   - Temporary buffers allocated per movie must be scoped within `@autoreleasepool` blocks to prevent memory leaks across multi-movie runs.

---

## 4. Fail-Closed Error Propagation & Non-Fallback Policy

The Metal backend follows a strict **Fail-Closed / Zero Silent Fallback** invariant:

1. **Unavailable / Unsupported Build**:
   - If `--metal` or `--metal_device` is requested on a binary compiled without `-DMETAL=ON`, the runner calls `REPORT_ERROR` and aborts with exit code 1. It **never** silently falls back to CPU.

2. **Device Discovery & Bounds**:
   - If no Metal devices are available (`metalGetDeviceCount() == 0`), aborts with:
     `ERROR: Metal requested but no compatible Metal devices were found on this system.`
   - If `device_id < 0 || device_id >= metalGetDeviceCount()`, aborts with:
     `ERROR: Invalid Metal device ID <id>. Found <N> Metal device(s).`

3. **Runtime Execution Faults**:
   - If device creation, buffer allocation, pipeline compilation, or command buffer submission fails, a `RelionError` must be thrown immediately.
   - The runner must never catch a Metal error and switch to CPU alignment silently.

4. **Mutual Exclusion**:
   - Specifying `--metal` with `--gpu` (CUDA) is rejected immediately with:
     `ERROR: Cannot specify both CUDA (--gpu) and Metal (--metal) backends simultaneously.`
   - Specifying `--metal` with `--use_motioncor2` is rejected immediately with:
     `ERROR: --metal is valid only with --use_own.`

---

## 5. Harness Provenance & Log Markers

For compatibility with automated verification harnesses (e.g., Issue #33 synthetic harness), the Metal backend emits the following required markers:

1. **Startup Device Marker (stdout)**:
   ```
   Using Metal acceleration on device <id> (<device_name>) for global alignment.
   ```

2. **Execution Smoke Marker (stdout)**:
   ```
   [Metal] Executed Metal dispatch smoke on device: <device_name>
   ```

3. **Logfile Profile Block (`<movie>.log`)**:
   ```
   [Metal Global Alignment Profile]
   Device: <device_name>
   Stage: <stage_description>
   Total Metal Alignment Time: <seconds> s
   ```
