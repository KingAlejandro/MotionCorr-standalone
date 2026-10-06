# nvTIFF LZW decode experiment — Issue #141

This implements a standalone GPU TIFF decoder and eligibility probe. It does
**not** add an nvTIFF route to `motioncorr`, change `--ingest auto`, or replace
LibTIFF. The project option is OFF by default and the executable is not installed.

## Build

Use Linux, CUDA Toolkit 12+, and a separately installed **nvTIFF 0.8** SDK.
The implementation targets the shipped 0.8.0.82 headers: that API selects images
by **IFD offset**, using `nvtiffDecodeParamsSetRegions`, rather than the older
index-based `nvtiffDecodeRange` API cited in the initial issue plan.

```sh
cmake -S experiments/nvtiff -B build-nvtiff \
  -DCMAKE_BUILD_TYPE=Release -DNVTIFF_ROOT=/path/to/nvidia/nvtiff
cmake --build build-nvtiff --parallel 2
```

Alternatively use `-DBUILD_NVTIFF_PROBE=ON` with the normal project build.
The standalone build requires neither the MotionCorr dependencies nor nvcc
compilation: it calls the SDK's existing decoder through its C API. CUDA runtime
and nvTIFF must still be found at configure time and by the dynamic loader.
nvCOMP is needed only if probing/decoding Deflate through nvTIFF; LZW has no
nvCOMP decoder. Record the actual libraries used, not just header versions.

nvTIFF is proprietary. No NVIDIA SDK/header/library is vendored or installed by
this change; its distribution terms and compatibility with this project's
GPL-2.0-or-later license remain a prerequisite for any production integration.
Keeping an experiment optional is not itself a license compatibility decision.

## Probe and decode

```sh
# Eligibility only; no image decode or output allocation.
build-nvtiff/motioncorr_nvtiff_probe --movie movie-lzw.tiff \
  --trusted-input --probe-only > eligibility.json

# Every native sample, in the existing oracle's MRC-bottom-up dump format.
# Destination must be new. No gain, floating-point expansion or motion correction.
build-nvtiff/motioncorr_nvtiff_probe --movie movie-lzw.tiff \
  --trusted-input --dump nvtiff-samples.bin > decode.json

# Use the existing independent tifffile/imagecodecs comparator for ALL frames.
python3 docs/input_backends/harness/compare_native_samples.py \
  movie-lzw.tiff nvtiff-samples.bin --json sample-comparison.json

# A selected frame range; indices are zero-based, unlike runner CLI frame indices.
build-nvtiff/motioncorr_nvtiff_probe --movie movie-lzw.tiff \
  --trusted-input --first 3 --count 5 --dump selected-samples.bin

# Timing arm: omit --dump to exclude device-to-host sample copies and disk writes.
build-nvtiff/motioncorr_nvtiff_probe --movie movie-lzw.tiff \
  --trusted-input --batch-frames 4 > decode-batch4.json
```

The existing comparator assumes the full movie. A selected dump must be compared
against the matching independent frame range; do not label its shape mismatch a
decoder failure, or count selected-range identity as all-frame identity.

## Contract

- Every directory is inspected before decoding any selected frames. Only uniform
  geometry/bit depth, unsigned 8/16-bit, one-channel MINISBLACK, contiguous planar
  configuration, depth one, top-left orientation and predictor 1/2 are admitted.
  Strip/tile and compression eligibility are then checked by the library for
  each image. Packed/signed/floating/palette/RGB/rotated/depth data are declined.
  The raw ImageDepth LONG tag defaults to one when absent. nvTIFF 0.8 reports
  geometry depth zero for those ordinary 2D files; an explicit non-unit raw
  depth or geometry depth greater than one is still declined.
- The input is read once into an immutable host snapshot; both metadata admission
  and decode use those same bytes. Default compressed-input cap: 1 GiB. The file
  must be regular, nonempty and not a symlink. This is not a malformed-stream
  safety proof, and the file-change check is not an atomic producer snapshot.
- `--trusted-input` is mandatory even for probing. Bounds and support checks do
  not validate compressed LZW/Deflate data. Use known controlled files in this
  research executable; no untrusted-file service is implied.
- Default batch: one image. Explicit device-output cap: 256 MiB. Both caps are
  configurable in bytes. A batch that nvTIFF cannot execute together is refused,
  rather than silently timed as several serial calls.
- Each decode is completed before decoder reuse/destruction, even when its
  immediate status fails. CUDA completion failure stops further dispatch.
  A failed context's device state is left to process exit, not reported as clean.
- The dump contains four little-endian int64 values (width, height, frame count,
  bytes/sample), then native sample bytes in frame/y/x order with rows flipped
  to match `rwTIFF`. The row convention is an implementation hypothesis until
  independently compared; the existing oracle includes its unflipped negative.
- A unique sibling temporary is published without overwriting any existing
  destination, after checked decoder/stream/output cleanup. There is no fsync
  durability claim. Errors are named on stderr with nonzero exit; unsupported
  admitted/library layouts return 3, accompanied by per-frame JSON statuses.

## Measurement boundaries and next acceptance

JSON separates admission wall, decode wall, CUDA-stream interval, optional
sample-copy wall, optional dump-write wall, and total process work wall. The CUDA
interval is not claimed to be pure kernel time. Standalone decode timing cannot
be subtracted from a MotionCorr wall time to establish an application speedup.
No timing runs or GPU correctness results are included in this implementation.

`output_device_bytes` is the explicit batch buffer; **nvTIFF internal scratch is
unknown**, represented by `decoder_internal_device_bytes: null`. It is neither
whole-process peak VRAM nor evidence of zero additional VRAM. The immutable
compressed snapshot uses host memory too. Measure actual process/GPU memory
during native execution before choosing movie batching or worker admission.

Before proposing a product route, complete #141's layout matrix, every-sample
independent oracle, range/orientation/byte-order/predictor controls, native
failure/cleanup controls and matched uint8/uint16 24/48-frame measurements.
Preserve the declared application threshold of at least 0.15 seconds/movie and
record code/input/binary/library hashes, UUID, affinity and occupied resources.
Promotion also requires the #134 trust decision, license review, bounded scratch
admission and full MotionCorr gain/sum/FFT/output comparisons. None is waived.

SDK reference: [NVIDIA nvTIFF](https://developer.nvidia.com/nvtiff),
[NVIDIA samples](https://github.com/NVIDIA/CUDALibrarySamples/tree/master/nvTIFF),
`nvidia-nvtiff-cu12` 0.8.0.82 wheel SHA256
`2d4a2ea3b749d78fe446df496235469a4cb71eb64deff907e74f02eaa4a70cdf`.
The source is compiled against those headers, rather than assuming an older
documentation signature still matches the installed SDK.
