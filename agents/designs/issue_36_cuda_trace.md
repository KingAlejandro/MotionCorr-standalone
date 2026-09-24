# Issue 36: opt-in CPU/CUDA numerical divergence trace

## Decision

Add a diagnostic-only, explicitly enabled trace that compares the CPU and CUDA global-alignment path for one selected movie and a bounded set of original movie frames. Use movie `00021` for the first investigation. Tracing must not alter calculations, scheduling, output files, or default behavior. Do not change Gate 2 tolerances or infer parity from the trace alone.

The trace is intended to identify the earliest stage whose values differ. It is not a production logging feature and must be off unless a user supplies an output directory and movie/frame selection. Reject an existing backend-specific trace file to prevent stale files from being mistaken for fresh evidence; the other backend's trace may share the directory.

## Trace selection and device contract

Select the movie by its canonical input path plus content hash, and frames by 1-based source-frame numbers after recording grouping, skipped-frame, and frame-index mapping. Default diagnostic selection is one frame and the first global-alignment iteration; permit explicit frame IDs and iteration IDs up to `max_iter`. This keeps the full-size experimental movie within the trace budget. Record all other frames' scalar shifts each iteration because reference formation reduces across all frames. Do not trace local patches by default; allow one explicitly selected patch as a later extension.

CUDA tracing must use the explicitly requested `--gpu` device. Record requested ordinal, resolved CUDA device name, PCI bus ID/UUID when available, and runtime/driver/cuFFT versions. If the requested GPU cannot be selected or CUDA execution markers are absent, fail the trace; CPU fallback must not masquerade as CUDA evidence. CPU and CUDA traces must use identical movie bytes, preprocessing/options, selected source frames, iteration count, and corresponding stage barriers.

## Stage checkpoints

For each selected frame and each global iteration, capture matching CPU and CUDA values at these checkpoints, in order:

1. Input `Fframes` immediately before reference formation (include every coefficient for selected frames).
2. `Fref` after reference reduction (capture the complete reference array; this depends on all movie frames).
3. `Fccs` after weighted cross-correlation spectrum formation for selected frames.
4. `Iccs` after inverse FFT and before peak search for selected frames.
5. Peak-search result: winning integer `(x,y)`, peak value, the five-point stencil (`center`, `x-`, `x+`, `y-`, `y+`), x/y curvature denominators, epsilon/fallback branch, unscaled and scaled subpixel shifts.
6. Accumulated/origin-adjusted per-frame shifts and post-global-shift `Fframes` after Fourier shifting (complete arrays for selected frames).
7. Final global trajectory passed to local alignment and the resulting local polynomial/model coefficients at the existing model-construction boundary.

Capture exact values in each backend's native computation precision, without rounding or recomputation. Also record dimensions, strides/layout, scalar type, FFT normalization/convention, iteration, frame mapping, and stage label. A NaN/Inf count and max-absolute-value summary may accompany data but may not replace it.

## Synchronization and trace format

CPU checkpoints occur after the producer loop/FFT completes and before the consumer stage begins. CUDA checkpoints occur after the producing kernel or cuFFT call and before the consumer; explicitly synchronize the selected stream before device-to-host copies. Do not add synchronization to non-tracing runs. The trace records synchronization/device-copy failures as incomplete and unusable rather than emitting a partial pass.

Write `motioncorr-cuda-trace` format version 1: one JSON manifest plus typed, endian-declared binary array chunks, with per-chunk shape, dtype, byte count, stage/frame/iteration key, and SHA-256. JSON stores command/options, source revision/build identity, input hash, backend/compiler/runtime versions, requested and resolved GPU identity, and chunk index. Avoid lossy compression. Pair CPU and CUDA chunks by stage key, not file order. A small comparison utility may report first unequal stage, max absolute/relative deltas, mismatch count, and peak/shift/model deltas; it must not decide Gate 2.

## Size, privacy, and provenance

Cap the trace at **256 MiB per backend** by default and refuse to start when the selected complete checkpoints exceed the cap. No silent truncation, sampling, or dropping of required chunks: instead reduce selected frames/iterations explicitly and record the selection. This bounded movie/frame/iteration selection avoids whole-movie multi-GB dumps. Keep traces local and opt-in; they contain derived Fourier/movie image data and must be treated as sensitive scientific input. Do not upload automatically. Preserve hashes and exact command/build/device provenance beside data; redact no values needed for reproducibility, but avoid embedding user names or unrelated environment variables.

## Acceptance

- With tracing disabled, output bytes, logs (apart from no new trace-related output), and numerical behavior remain unchanged.
- With tracing enabled, a fresh CPU/CUDA trace for movie 00021 contains all required matched checkpoints for the selected frames/iterations, passes chunk/hash/shape validation, and fits the declared per-backend cap.
- The comparator identifies the earliest stage with a nonzero difference (or reports equality through the captured stages), including all five peak samples, denominators, branch choice, and shifts; it never labels Gate 2 as passed.
- Requested GPU identity and real CUDA execution evidence are present; a missing device, failed copy/synchronization, incomplete trace, stale directory, or exceeded budget fails closed with an actionable error.
- No new movie processing run is part of this design approval; implementation validation should first use existing captured artifacts or a small explicitly authorized diagnostic run, then rerun the established full comparison before any parity claim.

## Implementation notes and unresolved interface choices

Place the opt-in selection/configuration at the runner boundary and keep serialization/comparison outside hot kernels where possible. The exact CLI spelling and chunk container library are implementation choices; prefer a dependency-free writer unless the repository already has an approved portable container. The existing code has both host and CUDA stage boundaries in `alignPatch`; local-model coefficient capture must be placed where global trajectories are consumed to construct the local model, without changing that model's calculation. If complete selected-frame spectra exceed budget, the operator must choose fewer frames or iterations; do not silently switch to a reduced view.

### Phase 1 delivered probe and limits

The first implementation is a small peak-decision probe, not the full raw-array trace specified above. It is enabled by `MOTIONCORR_PEAK_TRACE_DIR`, `MOTIONCORR_PEAK_TRACE_FRAME` (zero-based post-grouping ordinal), and `MOTIONCORR_PEAK_TRACE_ITER` (one-based). Run **one movie per process**: the probe does not select a movie from a multi-movie input and would refuse the second same-backend output. It records the runner's movie path as a label, with `input_content_hash: null`; operators must independently preserve input hashes and the exact command. The directory must already exist and may contain the other backend's trace; each backend file is created exclusively and cannot overwrite a stale file or symlink. This probe captures the actual peak/stencil/interpolation values and recentered shift for one frame/iteration, without intermediate arrays, local-model snapshots, or source-frame mapping. Do not use a Phase-1 trace alone to declare the first differing stage or Gate 2 status.
